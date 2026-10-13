"""Локальный стенд Mini App с подставными данными — посмотреть вёрстку без Telegram и панели.

    python scripts/dev_webapp.py [порт]   → http://127.0.0.1:4176/?u=new|active|expired

Страница получает initData, подписанную тестовым ключом, как настоящий Telegram.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MARAT_SITE_URL", "https://etalon.168.113.210.6.sslip.io")
os.environ.setdefault("MARAT_NAME", "Etalon VPN")

from aiohttp import web  # noqa: E402

from marat_bot import core, webapp  # noqa: E402

TOKEN = "1:dev"
USERS = {"new": 1001, "active": 1002, "expired": 1003}


def _init_data(uid: int) -> str:
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": "Марат", "username": "maratkam1"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    # Как Telegram: пробелы — %20, не «+» (в адресе «+» превратился бы в пробел и сломал подпись).
    signed = {**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()}
    return urllib.parse.urlencode(signed, quote_via=urllib.parse.quote)


def _fake_devices() -> str:
    path = os.path.join(tempfile.mkdtemp(), "devices.sqlite3")
    now = time.time()
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE devices (username TEXT, hwid TEXT, model TEXT, os TEXT, first_seen REAL, last_seen REAL)")
    conn.executemany("INSERT INTO devices VALUES (?,?,?,?,?,?)", [
        ("corp_mrt_1002", "a", "iPhone 15 Pro", "iOS 18.1", now - 9e5, now - 600),
        ("corp_mrt_1002", "b", "MacBook Air", "macOS 15", now - 9e5, now - 2 * 86400),
    ])
    conn.commit()
    conn.close()
    return path


async def main(port: int) -> None:
    webapp.DEVICE_DB = _fake_devices()
    now = int(time.time())
    accesses = {
        1002: core.Access("corp_mrt_1002", "Y29ycF9tcnRfMTAwMiwxNzkw", now + 2 * 86400 + 7 * 3600, "active", 3_400_000_000, 10 * 1024**3),
        1003: core.Access("corp_mrt_1003", "Y29ycF9tcnRfMTAwMywxNzkw", now - 86400, "expired", 9 * 1024**3, 10 * 1024**3),
    }

    async def my_access(uid):
        return accesses.get(uid)

    async def issue_trial(uid):
        accesses[uid] = core.Access(f"corp_mrt_{uid}", "TRIALTOKEN", now + 3 * 86400, "active", 0, 10 * 1024**3)
        return accesses[uid], True

    app = webapp.make_app(prefix="/mapp/etalon", bot_token=TOKEN, bot_username=lambda: "etallonvpn_bot",
                          my_access=my_access, issue_trial=issue_trial, support_available=lambda: True)

    async def home(request: web.Request) -> web.Response:
        uid = USERS.get(request.query.get("u", "active"), 1002)
        # Переход скриптом: HTTP-редирект aiohttp раскодирует %26/%3D во фрагменте и режет initData.
        target = "/mapp/etalon/#tgWebAppData=" + urllib.parse.quote(_init_data(uid), safe="")
        return web.Response(text=f"<script>location.replace({json.dumps(target)})</script>", content_type="text/html")

    app.router.add_get("/", home)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    print(f"стенд: http://127.0.0.1:{port}/?u=new|active|expired", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 4176))
