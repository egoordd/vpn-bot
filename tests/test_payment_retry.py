"""Оплата, выдача которой сорвалась, выдаётся на повторе вебхука.

До 22.09.2026 платёж к моменту выдачи уже числился проведённым, а отметка о
дубле стояла. Сбой панели давал 500, но повтор ЮKassa или Tribute отбрасывался —
деньги получены, подписки нет (аудит, BILL-01).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services import web_checkout
from services.payment import create_invoice_payload
from tests.test_http_api import api_client  # noqa: F401 - fixture


class _Redis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key):
        self.store.pop(key, None)


class _Sub:
    subscription_url = "https://23.95.3.18.sslip.io/sub/retry-token"
    expires_at = datetime(2026, 10, 22, tzinfo=timezone.utc)


def _flaky_activation():
    """Первая выдача падает (панель недоступна), вторая проходит."""
    calls = []

    async def activate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("panel down")
        return _Sub()

    return activate, calls


def _yookassa_paid(monkeypatch, api_mod, payment_id: str):
    monkeypatch.setattr(
        api_mod.yookassa, "get_payment",
        AsyncMock(return_value={"id": payment_id, "status": "succeeded", "amount": {"value": "149.00"}}),
    )


@pytest.mark.asyncio
async def test_a_failed_delivery_is_redelivered_on_the_next_webhook(api_client, session_pool, monkeypatch):  # noqa: F811
    from services import http_api as api_mod

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=880001)
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-retry-1",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_1m"), plan="standard_1m",
        )
    redis = _Redis()
    api_client._transport.app.state.redis = redis
    _yookassa_paid(monkeypatch, api_mod, "yk-retry-1")
    activate, calls = _flaky_activation()
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", deliver)

    first = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-retry-1"}})
    assert first.status_code == 500
    async with session_pool() as session:
        assert (await Repository(session).get_payment_by_external_id("yk-retry-1")).status == "pending"
    assert "yookassa:evt:yk-retry-1" not in redis.store

    second = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-retry-1"}})
    assert second.status_code == 200
    assert len(calls) == 2
    deliver.assert_awaited_once()
    async with session_pool() as session:
        assert (await Repository(session).get_payment_by_external_id("yk-retry-1")).status == "completed"


@pytest.mark.asyncio
async def test_an_email_order_is_redelivered_with_its_password(api_client, session_pool, monkeypatch):  # noqa: F811
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(api_mod.yookassa, "create_payment", AsyncMock(return_value={
        "id": "yk-retry-2", "status": "pending",
        "confirmation": {"confirmation_url": "https://yoomoney.ru/pay/yk-retry-2"},
    }))
    await api_client.post("/web/checkout", json={"plan": "standard_1m", "email": "retry@mail.ru"})
    api_client._transport.app.state.redis = _Redis()
    _yookassa_paid(monkeypatch, api_mod, "yk-retry-2")
    activate, calls = _flaky_activation()
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)
    letter = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.web_delivery, "send_subscription_letter", letter)

    assert (await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-retry-2"}})).status_code == 500
    async with session_pool() as session:
        checkout = await web_checkout.find_by_payment_id(session, "yk-retry-2")
        assert checkout.status == web_checkout.PENDING
    letter.assert_not_awaited()

    assert (await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-retry-2"}})).status_code == 200
    letter.assert_awaited_once()
    assert letter.await_args.kwargs["temporary_password"], "пароль придёт и после сорвавшейся первой выдачи"
    async with session_pool() as session:
        checkout = await web_checkout.find_by_payment_id(session, "yk-retry-2")
        assert checkout.status == web_checkout.COMPLETED


@pytest.mark.asyncio
async def test_tribute_retries_after_a_failed_delivery(api_client, monkeypatch):  # noqa: F811
    from services import http_api as api_mod

    redis = _Redis()
    api_client._transport.app.state.redis = redis
    monkeypatch.setattr(api_mod.tribute, "verify_signature", lambda raw, sig: True)
    monkeypatch.setattr(api_mod.tribute, "plan_for", lambda tribute_id: "standard_1m")
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", AsyncMock(return_value=True))
    activate, calls = _flaky_activation()
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)
    body = {"name": "new_subscription", "payload": {"telegram_user_id": 880002, "subscription_id": 5, "purchase_id": "p-1"}}

    assert (await api_client.post("/tribute/webhook", json=body)).status_code == 500
    assert redis.store == {}, "отметка о дубле снята — Tribute повторит"
    assert (await api_client.post("/tribute/webhook", json=body)).status_code == 200
    assert len(calls) == 2
