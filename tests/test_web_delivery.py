"""A site purchase must reach the buyer even when the success page cannot.

On a phone the payment often finishes in the bank's app and returns in another
browser, where the success page had no idea which order to show. Two fixes are
held here: the return address names the order, and the link goes out by email.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services import web_delivery
from tests.test_http_api import api_client  # noqa: F401 - fixture


def test_the_letter_carries_everything_needed_to_connect(monkeypatch):
    monkeypatch.setattr(web_delivery.settings, "WEB_BASE_URL", "https://unlockproject.site")
    link = "https://unlockru.site/sub/TOKEN"

    subject, text, body = web_delivery.build_letter(
        link, "Standard 1 месяц", datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
    )

    for part in (text, body):
        assert link in part
        assert "https://unlockproject.site/connect#sub=https%3A%2F%2Funlockru.site%2Fsub%2FTOKEN" in part
        assert "/cabinet" in part
        assert "/link" in part
        assert "11.10.2026" in part
        assert "unlockvpn.site" not in part
    assert "UnLock VPN" in subject


@pytest.mark.asyncio
async def test_no_mail_server_means_no_claimed_delivery(monkeypatch):
    monkeypatch.setattr(web_delivery.mailer, "is_configured", lambda: False)

    assert not await web_delivery.send_subscription_letter("a@b.ru", "https://x/sub/t", "P", None)


@pytest.mark.asyncio
async def test_a_failing_mailer_never_breaks_the_payment(monkeypatch):
    monkeypatch.setattr(web_delivery.mailer, "is_configured", lambda: True)
    monkeypatch.setattr(web_delivery.mailer, "send_email", AsyncMock(side_effect=OSError("smtp down")))

    assert not await web_delivery.send_subscription_letter("a@b.ru", "https://x/sub/t", "P", None)


@pytest.mark.asyncio
async def test_the_return_address_names_the_order(api_client, session_pool, monkeypatch):  # noqa: F811
    from services import http_api as api_mod

    captured = {}

    async def create_payment(**kwargs):
        captured.update(kwargs)
        return {"id": "yk-ret-1", "status": "pending", "confirmation": {"confirmation_url": "https://yoomoney.ru/x"}}

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(api_mod.yookassa, "create_payment", create_payment)
    import config

    real_settings = config.get_settings

    def site_settings():
        current = real_settings()
        current.WEB_BASE_URL = "https://unlockproject.site"
        return current

    monkeypatch.setattr(config, "get_settings", site_settings)

    response = await api_client.post("/web/checkout", json={"plan": "standard_1m", "email": "buyer@mail.ru"})

    assert response.status_code == 200
    return_url = captured["return_url"]
    assert return_url.startswith("https://unlockproject.site/pay/success?order=")
    token = return_url.rsplit("=", 1)[1]
    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("yk-ret-1")
    assert payment.invoice_payload.endswith(f":{token}")


@pytest.mark.asyncio
async def test_the_order_is_found_by_the_token_in_the_return_address(
    api_client, session_pool, monkeypatch  # noqa: F811
):
    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=-515151)
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-tok-1",
            invoice_payload=payload, plan="standard_1m",
        )
    token = payload.rsplit(":", 1)[1]

    pending = await api_client.get(f"/web/order/{token}")
    assert pending.status_code == 200
    assert pending.json() == {"status": "pending"}

    unknown = await api_client.get(f"/web/order/{'0' * 32}")
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_an_email_buyer_gets_the_link_by_letter(api_client, session_pool, monkeypatch):  # noqa: F811
    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=-626262)
        await repo.update_user(user.id, email="buyer@mail.ru")
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-mail-1",
            invoice_payload=payload, plan="standard_1m",
        )

    monkeypatch.setattr(
        api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-mail-1", "status": "succeeded"})
    )

    class _Sub:
        subscription_url = "https://144.172.101.217.sslip.io:8443/sub/web-token"
        expires_at = datetime(2026, 10, 11, tzinfo=timezone.utc)

    monkeypatch.setattr(api_mod, "activate_panel_subscription", AsyncMock(return_value=_Sub()))
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", AsyncMock(return_value=True))
    letter = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.web_delivery, "send_subscription_letter", letter)

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-mail-1"}})

    assert response.status_code == 200
    letter.assert_awaited_once()
    email, sub_url, _title, _expires = letter.await_args.args
    assert email == "buyer@mail.ru"
    assert sub_url.endswith("/sub/web-token")


@pytest.mark.asyncio
async def test_a_telegram_buyer_is_not_mailed_twice(api_client, session_pool, monkeypatch):  # noqa: F811
    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=727272)
        await repo.update_user(user.id, email="tg@mail.ru")
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-mail-2",
            invoice_payload=payload, plan="standard_1m",
        )

    monkeypatch.setattr(
        api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-mail-2", "status": "succeeded"})
    )

    class _Sub:
        subscription_url = "https://144.172.101.217.sslip.io:8443/sub/tg-token"
        expires_at = datetime(2026, 10, 11, tzinfo=timezone.utc)

    monkeypatch.setattr(api_mod, "activate_panel_subscription", AsyncMock(return_value=_Sub()))
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", AsyncMock(return_value=True))
    letter = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.web_delivery, "send_subscription_letter", letter)

    await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-mail-2"}})

    letter.assert_not_awaited()
