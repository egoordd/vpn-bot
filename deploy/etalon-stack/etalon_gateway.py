"""Шлюз подписок Etalon VPN — собственная установка заказчика (15.10.2026).

Берёт подписку пользователя у своей панели Marzban и отдаёт её клиенту:
- Happ — JSON-конфиги xray: «⚡️ Авто-выбор» (балансировщик между странами),
  «🇷🇺 Режим РУ-сервисов» и по пункту на страну (xray_json.build_json_subscription);
- остальным приложениям — обычный base64-список ссылок;
- истёкшая подписка — пустой список (Marzban отдаёт ссылки и после срока);
- лимит устройств: приложение присылает x-hwid, устройства хранятся в DEVICE_DB (схема та же, что
  читает мини-приложение бота). Пробный период (в подписке есть лимит трафика) — GW_TRIAL_DEVICES,
  оплаченный — GW_PAID_DEVICES. Лишнее устройство получает одну запись «Лимит устройств» вместо
  серверов; приложения без x-hwid не блокируются; устройство без обращений DEVICE_IDLE_DAYS освобождает место.

Только стандартная библиотека Python. Слушает 127.0.0.1 (по умолчанию :2096); снаружи до него
доходят через nginx на московском входе. Настройки — переменные окружения GW_* (etalon-gateway.env).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xray_json import build_json_subscription

log = logging.getLogger("etalon-gateway")

LISTEN = os.environ.get("GW_LISTEN", "127.0.0.1:2096")
MARZBAN = os.environ.get("GW_MARZBAN", "http://127.0.0.1:8000").rstrip("/")
TITLE = os.environ.get("GW_TITLE", "Etalon VPN")
AUTO_TITLE = os.environ.get("GW_AUTO_TITLE", "⚡️ Авто-выбор")
SUPPORT_URL = os.environ.get("GW_SUPPORT_URL", "")
WEB_URL = os.environ.get("GW_WEB_URL", "")
UPDATE_HOURS = os.environ.get("GW_UPDATE_HOURS", "12")

DEVICE_DB = os.environ.get("GW_DEVICE_DB", "/var/lib/etalon-gateway/devices.sqlite3")
TRIAL_DEVICES = int(os.environ.get("GW_TRIAL_DEVICES", "2"))
PAID_DEVICES = int(os.environ.get("GW_PAID_DEVICES", "5"))
DEVICE_IDLE_DAYS = int(os.environ.get("GW_DEVICE_IDLE_DAYS", "14"))
LIMIT_REMARK = os.environ.get("GW_LIMIT_REMARK", "⛔️ Лимит устройств — напишите в поддержку")
FIELD_MAX = 128
_DEVICE_LOCK = threading.Lock()

SUB_PATH = re.compile(r"^/sub/([A-Za-z0-9_\-=]{10,300})/?$")
JSON_CLIENTS = ("happ",)
LINK_SCHEMES = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://")


def fetch_upstream(token: str) -> tuple[list[str], str | None] | None:
    """Ссылки пользователя и его subscription-userinfo из Marzban; None — такого токена нет."""
    req = urllib.request.Request(f"{MARZBAN}/sub/{token}", headers={"User-Agent": "v2rayN/7.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", "replace").strip()
            userinfo = resp.headers.get("subscription-userinfo")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return None
        raise
    try:
        text = base64.b64decode(raw + "===").decode("utf-8", "replace")
    except ValueError:
        text = raw
    links = [line.strip() for line in text.splitlines() if line.strip().startswith(LINK_SCHEMES)]
    return links, userinfo


def expired(userinfo: str | None) -> bool:
    match = re.search(r"expire=(\d+)", userinfo or "")
    return bool(match) and 0 < int(match.group(1)) < time.time()


def token_username(token: str) -> str | None:
    """Имя пользователя из токена Marzban: base64url(«имя,время») и 10 символов подписи."""
    try:
        data = token[:-10]
        decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    name, sep, stamp = decoded.partition(",")
    return name if sep and name and stamp.isdigit() else None


def _plan_limit(userinfo: str | None) -> int:
    match = re.search(r"total=(\d+)", userinfo or "")
    return TRIAL_DEVICES if match and int(match.group(1)) > 0 else PAID_DEVICES


def _store() -> sqlite3.Connection:
    directory = os.path.dirname(DEVICE_DB)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DEVICE_DB, timeout=5)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS devices ("
        " username TEXT NOT NULL, hwid TEXT NOT NULL, model TEXT, os TEXT,"
        " first_seen REAL NOT NULL, last_seen REAL NOT NULL,"
        " PRIMARY KEY (username, hwid))"
    )
    return conn


def device_allowed(username: str, hwid: str, limit: int, model: str | None = None, os_name: str | None = None) -> bool:
    """Запомнить устройство; False — оно сверх лимита. Ошибка хранилища — в пользу пользователя."""
    if limit <= 0:
        return True
    hwid, model, os_name = hwid[:FIELD_MAX], (model or "")[:FIELD_MAX] or None, (os_name or "")[:FIELD_MAX] or None
    now = time.time()
    try:
        with _DEVICE_LOCK:
            conn = _store()
            try:
                conn.execute("DELETE FROM devices WHERE last_seen < ?", (now - DEVICE_IDLE_DAYS * 86400,))
                known = conn.execute("SELECT 1 FROM devices WHERE username = ? AND hwid = ?", (username, hwid)).fetchone()
                if known is None:
                    used = conn.execute("SELECT COUNT(*) FROM devices WHERE username = ?", (username,)).fetchone()[0]
                    if used >= limit:
                        conn.commit()
                        log.info("device limit: %s %d/%d", username, used, limit)
                        return False
                    conn.execute(
                        "INSERT INTO devices (username, hwid, model, os, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                        (username, hwid, model, os_name, now, now),
                    )
                else:
                    conn.execute(
                        "UPDATE devices SET last_seen = ?, model = COALESCE(?, model), os = COALESCE(?, os)"
                        " WHERE username = ? AND hwid = ?",
                        (now, model, os_name, username, hwid),
                    )
                conn.commit()
            finally:
                conn.close()
    except sqlite3.Error:
        log.exception("device store failed, allowing")
    return True


def devices(username: str) -> list[str]:
    conn = _store()
    try:
        return [row[0] for row in conn.execute("SELECT hwid FROM devices WHERE username = ?", (username,))]
    finally:
        conn.close()


def _limit_body() -> bytes:
    link = ("vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1?security=none&type=tcp&encryption=none#"
            + urllib.parse.quote(LIMIT_REMARK))
    return base64.b64encode(link.encode())


def _b64(text: str) -> str:
    return "base64:" + base64.b64encode(text.encode()).decode()


def render(path: str, user_agent: str, client_headers: dict | None = None) -> tuple[int, dict[str, str], bytes]:
    """(статус, заголовки, тело) ответа на GET path; client_headers — заголовки запроса (x-hwid и др.)."""
    client_headers = {k.lower(): v for k, v in (client_headers or {}).items()}
    match = SUB_PATH.match(path.split("?", 1)[0])
    if not match:
        return 404, {"Content-Type": "text/plain"}, b"not found\n"
    token = match.group(1)
    upstream = fetch_upstream(token)
    if upstream is None:
        return 404, {"Content-Type": "text/plain"}, b"not found\n"
    links, userinfo = upstream
    if expired(userinfo):
        links = []
    headers = {
        "Cache-Control": "no-store",
        "profile-title": _b64(TITLE),
        "profile-update-interval": UPDATE_HOURS,
    }
    if userinfo:
        headers["subscription-userinfo"] = userinfo
    if SUPPORT_URL:
        headers["support-url"] = SUPPORT_URL
    if WEB_URL:
        headers["profile-web-page-url"] = WEB_URL
    hwid = (client_headers.get("x-hwid") or "").strip()
    username = token_username(token)
    if links and hwid and username and not device_allowed(
        username, hwid, _plan_limit(userinfo), client_headers.get("x-device-model"), client_headers.get("x-device-os")
    ):
        headers["Content-Type"] = "text/plain; charset=utf-8"
        return 200, headers, _limit_body()
    configs = []
    if links and any(client in user_agent.lower() for client in JSON_CLIENTS):
        configs = build_json_subscription(links, split=True, auto_remarks=AUTO_TITLE)
    if configs:
        headers["Content-Type"] = "application/json; charset=utf-8"
        return 200, headers, json.dumps(configs, ensure_ascii=False, separators=(",", ":")).encode()
    headers["Content-Type"] = "text/plain; charset=utf-8"
    return 200, headers, base64.b64encode("\n".join(links).encode())


class Handler(BaseHTTPRequestHandler):
    server_version = "nginx"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 — имя задаёт http.server
        try:
            status, headers, body = render(self.path, self.headers.get("User-Agent", ""), dict(self.headers.items()))
        except Exception:
            log.exception("subscription request failed")
            status, headers, body = 502, {"Content-Type": "text/plain"}, b"temporarily unavailable\n"
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # Токен подписки в журнал не пишем — только статус и приложение.
        log.info("%s %s", args[1] if len(args) > 1 else "-", self.headers.get("User-Agent", "-")[:40])


USAGE = """Использование:
  etalon_gateway.py                       — запустить шлюз (так его запускает служба)
  etalon_gateway.py devices ИМЯ           — устройства пользователя (имя как в панели, напр. corp_mrt_123)
  etalon_gateway.py forget ИМЯ [HWID]     — забыть устройства пользователя (или одно устройство)"""


def cli(args: list[str]) -> int:
    """Команды для поддержки: посмотреть и сбросить устройства пользователя."""
    if len(args) >= 2 and args[0] == "devices":
        conn = _store()
        try:
            rows = conn.execute(
                "SELECT hwid, model, os, last_seen FROM devices WHERE username = ? ORDER BY last_seen DESC", (args[1],)
            ).fetchall()
        finally:
            conn.close()
        for hwid, model, os_name, seen in rows:
            print(f"{hwid}\t{model or '—'}\t{os_name or '—'}\t{time.strftime('%d.%m.%Y %H:%M', time.localtime(seen))}")
        print(f"всего: {len(rows)}")
        return 0
    if len(args) in (2, 3) and args[0] == "forget":
        conn = _store()
        try:
            if len(args) == 3:
                n = conn.execute("DELETE FROM devices WHERE username = ? AND hwid = ?", (args[1], args[2])).rowcount
            else:
                n = conn.execute("DELETE FROM devices WHERE username = ?", (args[1],)).rowcount
            conn.commit()
        finally:
            conn.close()
        print(f"удалено устройств: {n}")
        return 0
    print(USAGE)
    return 2


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, port = LISTEN.rsplit(":", 1)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        raise SystemExit(cli(sys.argv[1:]))
    main()
