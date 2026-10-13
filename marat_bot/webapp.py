"""Telegram Mini App бота (14.10.2026, первым — «Etalon VPN»).

Кнопка «Открыть VPN» у поля ввода и в меню бота открывает страницу с доступом
человека: сколько дней осталось, статус, устройства, тарифы, ссылка, документы.
Страница и её API живут в том же процессе, что бот (aiohttp, свой порт), за
префиксом MARAT_WEBAPP_PREFIX — снаружи их отдаёт российский фронт VK (/mapp/)
через Caddy бот-сервера, поэтому приложение открывается и без включённого VPN.

Кто открыл приложение, узнаём по initData Telegram: подпись HMAC от ключа бота
(https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
Без верной подписи API ничего не отдаёт.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
import urllib.parse
from dataclasses import dataclass
from typing import Awaitable, Callable

from aiohttp import web

from marat_bot import docs
from marat_bot.core import DEVICES, NAME, PLANS, TRIAL_DAYS, TRIAL_TRAFFIC_BYTES, Access, per_month, sub_link

log = logging.getLogger("marat_bot.webapp")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
INIT_DATA_MAX_AGE = 24 * 3600
# Устройства считает шлюз подписок; база открыта всем на чтение. Устройство, не
# заходившее DEVICE_IDLE_DAYS, место больше не занимает — как в самом шлюзе.
DEVICE_DB = os.environ.get("MARAT_DEVICE_DB", "/var/lib/unlock-subgw/devices.sqlite3")
DEVICE_IDLE_DAYS = int(os.environ.get("MARAT_DEVICE_IDLE_DAYS", "14"))


def verify_init_data(init_data: str, bot_token: str, now: float | None = None,
                     max_age: int = INIT_DATA_MAX_AGE) -> dict | None:
    """Пользователь Telegram из initData или None, если подпись не сходится или данные старые."""
    if not init_data or not bot_token:
        return None
    pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    fields = dict(pairs)
    received = fields.pop("hash", "")
    if not received or len(pairs) != len(fields) + 1:
        return None
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        auth_date = int(fields.get("auth_date", "0"))
        user = json.loads(fields.get("user", "{}"))
    except (ValueError, json.JSONDecodeError):
        return None
    if (now if now is not None else time.time()) - auth_date > max_age or not isinstance(user.get("id"), int):
        return None
    return user


@dataclass(frozen=True)
class Device:
    model: str
    os: str
    last_seen: float


def devices_of(username: str, now: float | None = None, path: str | None = None) -> list[Device]:
    """Устройства подписки из учёта шлюза (только чтение; нет базы — пустой список)."""
    db = path or DEVICE_DB
    if not os.path.exists(db):
        return []
    since = (now if now is not None else time.time()) - DEVICE_IDLE_DAYS * 86400
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            rows = conn.execute(
                "SELECT model, os, last_seen FROM devices WHERE username = ? AND last_seen >= ? ORDER BY last_seen DESC",
                (username, since),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        log.exception("device registry read failed")
        return []
    return [Device(model or "Устройство", os_name or "", float(seen)) for model, os_name, seen in rows]


def access_payload(access: Access, now: float | None = None) -> dict:
    now = now if now is not None else time.time()
    seconds_left = max(0, int((access.expire or now) - now)) if access.expire else None
    devices = devices_of(access.username, now)
    return {
        "active": access.active,
        "status": access.status if access.active or access.status != "active" else "expired",
        "expire": access.expire,
        "seconds_left": seconds_left,
        "days_left": None if seconds_left is None else seconds_left // 86400,
        "hours_left": None if seconds_left is None else seconds_left % 86400 // 3600,
        "used_bytes": access.used_bytes,
        "limit_bytes": access.limit_bytes,
        "device_limit": DEVICES,
        "devices": [{"model": d.model, "os": d.os, "last_seen": int(d.last_seen)} for d in devices],
        "sub_url": sub_link(access.token) if access.token else None,
    }


AccessFn = Callable[[int], Awaitable[Access | None]]
TrialFn = Callable[[int], Awaitable[tuple[Access | None, bool]]]


def make_app(*, prefix: str, bot_token: str, bot_username: Callable[[], str], my_access: AccessFn,
             issue_trial: TrialFn, support_available: Callable[[], bool]) -> web.Application:
    prefix = "/" + prefix.strip("/")
    app = web.Application(client_max_size=64 * 1024)

    def user_of(request: web.Request, body: dict) -> dict:
        user = verify_init_data(str(body.get("initData") or ""), bot_token)
        if user is None:
            raise web.HTTPUnauthorized(text="bad init data")
        return user

    async def read_body(request: web.Request) -> dict:
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            raise web.HTTPBadRequest(text="json expected")
        return data if isinstance(data, dict) else {}

    def state(user: dict, access: Access | None) -> dict:
        username = bot_username()
        uid = user["id"]
        return {
            "name": NAME,
            "user": {"id": uid, "first_name": user.get("first_name") or "", "username": user.get("username") or ""},
            "bot": username,
            "access": access_payload(access) if access else None,
            # Пробник один на аккаунт: есть учётка (даже истёкшая) — повторно не выдаём, как и бот.
            "trial": {"available": access is None, "days": TRIAL_DAYS,
                      "devices": DEVICES, "gb": TRIAL_TRAFFIC_BYTES // 1024**3},
            "plans": [{"label": label, "days": days, "price": price, "per_month": per_month(days, price)}
                      for days, label, price in PLANS],
            "referral_link": f"https://t.me/{username}?start=ref{uid}" if username else None,
            "support_link": f"https://t.me/{username}?start=support" if username and support_available() else None,
            "docs": docs.links(),
        }

    async def me(request: web.Request) -> web.Response:
        user = user_of(request, await read_body(request))
        return web.json_response(state(user, await my_access(user["id"])))

    async def trial(request: web.Request) -> web.Response:
        user = user_of(request, await read_body(request))
        try:
            access, issued = await issue_trial(user["id"])
        except Exception:
            log.exception("webapp trial failed for %s", user["id"])
            return web.json_response({"error": "Не получилось — попробуйте через минуту."}, status=502)
        log.info("webapp trial for %s: issued=%s", user["id"], issued)
        return web.json_response({"issued": issued, **state(user, access)})

    page = _versioned_index()

    async def index(request: web.Request) -> web.Response:
        response = web.Response(text=page, content_type="text/html")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"
        )
        return response

    async def to_slash(request: web.Request) -> web.Response:
        raise web.HTTPMovedPermanently(prefix + "/")

    app.router.add_get(prefix, to_slash)
    app.router.add_get(prefix + "/", index)
    app.router.add_post(prefix + "/api/me", me)
    app.router.add_post(prefix + "/api/trial", trial)
    app.router.add_static(prefix + "/static/", os.path.join(STATIC_DIR, "static"), append_version=False)
    return app


def _versioned_index() -> str:
    """index.html со ссылками static/app.css?v=<хеш>: Telegram держит файлы в кэше, а после
    выкладки должен взять свежие."""
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    for name in ("app.css", "app.js"):
        with open(os.path.join(STATIC_DIR, "static", name), "rb") as fh:
            version = hashlib.sha256(fh.read()).hexdigest()[:10]
        page = page.replace(f"static/{name}", f"static/{name}?v={version}")
    return page


async def start(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    log.info("webapp listening on 127.0.0.1:%s", port)
    return runner
