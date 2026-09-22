"""Сессии сайта гаснут со сменой пароля и по «выйти на всех устройствах» (аудит 22.09.2026, SEC-04)."""

from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services import account_link, web_passwords
from tests.test_http_api import api_client  # noqa: F401 - fixture


async def _register(client, email: str, password: str = "first-pass1") -> int:
    response = await client.post("/web/auth/register", json={"email": email, "password": password})
    return response.json()["telegramId"]


async def _stamp(client, telegram_id: int):
    response = await client.get(f"/web/auth/stamp/{telegram_id}")
    return response.json().get("stamp") if response.status_code == 200 else response.status_code


@pytest.mark.asyncio
async def test_the_stamp_holds_while_nothing_changes(api_client):  # noqa: F811
    account = await _register(api_client, "steady@mail.ru")

    first = await _stamp(api_client, account)
    await api_client.post("/web/auth/login", json={"email": "steady@mail.ru", "password": "first-pass1"})

    assert isinstance(first, str) and len(first) == 32
    assert await _stamp(api_client, account) == first


@pytest.mark.asyncio
async def test_changing_the_password_ends_other_sessions(api_client):  # noqa: F811
    account = await _register(api_client, "change-s@mail.ru")
    before = await _stamp(api_client, account)

    await api_client.post(
        "/web/auth/password",
        json={"telegramId": account, "currentPassword": "first-pass1", "newPassword": "second-pass1"},
    )

    assert await _stamp(api_client, account) != before


@pytest.mark.asyncio
async def test_a_password_reset_ends_the_stolen_session(api_client, monkeypatch):  # noqa: F811
    from services import web_account_routes

    account = await _register(api_client, "stolen@mail.ru")
    stolen = await _stamp(api_client, account)
    monkeypatch.setattr(web_account_routes.mailer, "is_configured", lambda: True)
    sent = AsyncMock()
    monkeypatch.setattr(web_account_routes.web_delivery, "send_reset_letter", sent)

    await api_client.post("/web/auth/forgot", json={"email": "stolen@mail.ru"})
    _, token = sent.await_args.args
    await api_client.post("/web/auth/reset", json={"token": token, "password": "new-pass-12"})

    assert await _stamp(api_client, account) != stolen


@pytest.mark.asyncio
async def test_sign_out_everywhere_ends_every_session(api_client):  # noqa: F811
    account = await _register(api_client, "everywhere@mail.ru")
    before = await _stamp(api_client, account)

    response = await api_client.post("/web/auth/sign-out-everywhere", json={"telegramId": account})
    after = await _stamp(api_client, account)
    await api_client.post("/web/auth/sign-out-everywhere", json={"telegramId": account})

    assert response.json() == {"ok": True}
    assert after != before
    assert await _stamp(api_client, account) not in (before, after)


@pytest.mark.asyncio
async def test_an_unknown_account_has_no_stamp(api_client):  # noqa: F811
    assert await _stamp(api_client, -424242) == 404
    response = await api_client.post("/web/auth/sign-out-everywhere", json={"telegramId": -424242})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_an_absorbed_site_account_loses_its_sessions(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        web_user = await repo.create_user(telegram_id=-8801)
        await repo.update_user(web_user.id, email="merge@mail.ru", web_password_hash="hash")
        before = await web_passwords.session_stamp(session, -8801)

        await account_link.attach_telegram_to_web_account(
            session, web_telegram_id=-8801, telegram_id=8801, username="merger"
        )

        assert await web_passwords.session_stamp(session, -8801) != before
