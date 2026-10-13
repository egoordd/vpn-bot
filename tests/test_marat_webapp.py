"""Mini App бота (14.10.2026): подпись Telegram, API доступа, устройства, страница."""
import asyncio
import hashlib
import hmac
import json
import sqlite3
import time
import urllib.parse

from aiohttp.test_utils import TestClient, TestServer

from marat_bot import core, webapp

TOKEN = "123456:TEST-token"


def _init_data(user: dict, token: str = TOKEN, auth_date: int | None = None, tamper: bool = False) -> str:
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAE", "user": json.dumps(user)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({**user, "id": 999})
    return urllib.parse.urlencode({**fields, "hash": digest})


def test_valid_init_data_gives_the_user():
    assert webapp.verify_init_data(_init_data({"id": 5, "first_name": "Ира"}), TOKEN)["id"] == 5


def test_forged_old_or_foreign_init_data_is_rejected():
    user = {"id": 5}
    assert webapp.verify_init_data(_init_data(user, tamper=True), TOKEN) is None, "подменённый пользователь"
    assert webapp.verify_init_data(_init_data(user, token="other:bot"), TOKEN) is None, "подпись другого бота"
    old = int(time.time()) - webapp.INIT_DATA_MAX_AGE - 10
    assert webapp.verify_init_data(_init_data(user, auth_date=old), TOKEN) is None, "старые данные"
    assert webapp.verify_init_data("", TOKEN) is None and webapp.verify_init_data("user=1", TOKEN) is None


def _devices_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE devices ( username TEXT NOT NULL, hwid TEXT NOT NULL, model TEXT, os TEXT, "
                 "first_seen REAL NOT NULL, last_seen REAL NOT NULL, PRIMARY KEY (username, hwid))")
    conn.executemany("INSERT INTO devices VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_devices_come_from_the_gateway_registry_without_idle_ones(tmp_path):
    db = str(tmp_path / "devices.sqlite3")
    now = time.time()
    _devices_db(db, [
        ("corp_mrt_5", "a", "iPhone 15", "iOS", now - 9e5, now - 3600),
        ("corp_mrt_5", "b", "Pixel 8", "Android", now - 9e6, now - 20 * 86400),
        ("corp_mrt_6", "c", "MacBook", "macOS", now, now),
    ])
    found = webapp.devices_of("corp_mrt_5", now, path=db)
    assert [d.model for d in found] == ["iPhone 15"], "простаивающее 20 дней место не занимает, чужие не видны"
    assert webapp.devices_of("corp_mrt_5", now, path=str(tmp_path / "nope.sqlite3")) == []


def _app(access=None, issued=True):
    calls = []

    async def my_access(uid):
        return access

    async def issue_trial(uid):
        calls.append(uid)
        granted = core.Access(f"corp_mrt_{uid}", "TOK", int(time.time()) + 3 * 86400, "active", 0, 10 * 1024**3)
        return granted, issued

    application = webapp.make_app(prefix="/mapp/etalon", bot_token=TOKEN, bot_username=lambda: "etallonvpn_bot",
                                  my_access=my_access, issue_trial=issue_trial, support_available=lambda: True)
    return application, calls


def _run(application, scenario):
    async def go():
        client = TestClient(TestServer(application))
        await client.start_server()
        try:
            return await scenario(client)
        finally:
            await client.close()
    return asyncio.run(go())


def test_me_needs_a_valid_signature_and_describes_a_new_user():
    application, _ = _app()

    async def scenario(client):
        denied = await client.post("/mapp/etalon/api/me", json={"initData": "user=%7B%22id%22%3A5%7D&hash=0"})
        ok = await client.post("/mapp/etalon/api/me", json={"initData": _init_data({"id": 5, "first_name": "Ира"})})
        return denied.status, ok.status, await ok.json()

    denied, status, body = _run(application, scenario)
    assert denied == 401 and status == 200
    assert body["access"] is None and body["trial"]["available"] is True
    assert body["referral_link"] == "https://t.me/etallonvpn_bot?start=ref5"
    assert body["support_link"] == "https://t.me/etallonvpn_bot?start=support"
    assert [p["price"] for p in body["plans"]] == [price for _, _, price in core.PLANS]


def test_me_shows_days_left_and_link_for_an_active_user():
    access = core.Access("corp_mrt_5", "TOK", int(time.time()) + 2 * 86400 + 5 * 3600, "active", 2 * 1024**3, 10 * 1024**3)
    application, _ = _app(access)

    async def scenario(client):
        r = await client.post("/mapp/etalon/api/me", json={"initData": _init_data({"id": 5})})
        return await r.json()

    a = _run(application, scenario)["access"]
    assert a["active"] and a["days_left"] == 2 and a["hours_left"] in (4, 5)
    assert a["sub_url"] == core.sub_link("TOK") and a["device_limit"] == core.DEVICES


def test_expired_access_reports_expired_and_no_trial():
    access = core.Access("corp_mrt_5", "TOK", int(time.time()) - 60, "active", 0, 10 * 1024**3)
    application, _ = _app(access)

    async def scenario(client):
        r = await client.post("/mapp/etalon/api/me", json={"initData": _init_data({"id": 5})})
        return await r.json()

    body = _run(application, scenario)
    assert body["access"]["active"] is False and body["access"]["status"] == "expired"
    assert body["trial"]["available"] is False, "пробник один на аккаунт"


def test_trial_is_issued_for_the_signed_user_only():
    application, calls = _app()

    async def scenario(client):
        bad = await client.post("/mapp/etalon/api/trial", json={"initData": _init_data({"id": 5}, tamper=True)})
        good = await client.post("/mapp/etalon/api/trial", json={"initData": _init_data({"id": 5})})
        return bad.status, good.status, await good.json()

    bad, good, body = _run(application, scenario)
    assert bad == 401 and good == 200 and calls == [5]
    assert body["issued"] is True and body["access"]["active"] is True


def test_page_and_assets_are_served_with_a_tight_policy():
    application, _ = _app()

    async def scenario(client):
        page = await client.get("/mapp/etalon/")
        js = await client.get("/mapp/etalon/static/app.js")
        bare = await client.get("/mapp/etalon", allow_redirects=False)
        return page.status, page.headers.get("Content-Security-Policy", ""), await page.text(), js.status, bare.status

    status, csp, html, js, bare = _run(application, scenario)
    assert status == 200 and js == 200 and bare == 301
    assert "telegram-web-app.js" in html and "static/app.js" in html
    assert "script-src 'self' https://telegram.org" in csp and "connect-src 'self'" in csp


def test_menu_offers_the_app_only_when_configured(monkeypatch):
    from marat_bot import keyboards as kb

    monkeypatch.setattr(kb, "WEBAPP_URL", "")
    assert not any("web_app" in b for row in kb.main(None)["inline_keyboard"] for b in row)
    monkeypatch.setattr(kb, "WEBAPP_URL", "https://m.example/mapp/etalon/")
    rows = kb.main(None)["inline_keyboard"]
    assert rows[1][0]["web_app"] == {"url": "https://m.example/mapp/etalon/"}, "сразу под главной кнопкой"


def test_assets_are_versioned_so_telegram_takes_fresh_ones():
    page = webapp._versioned_index()
    assert "static/app.css?v=" in page and "static/app.js?v=" in page
