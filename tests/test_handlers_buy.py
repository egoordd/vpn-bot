from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import buy
from database.repository import Repository


@pytest.mark.integration
async def test_buy_plan_handler_creates_invoice_and_payment(session_pool, fake_bot, monkeypatch):
    callback = SimpleNamespace(
        data="buy:1m",
        from_user=SimpleNamespace(id=910, username="buyer"),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    create_invoice = AsyncMock(return_value={"invoice_id": "ext-1", "pay_url": "https://pay.example"})
    monkeypatch.setattr(buy, "create_invoice", create_invoice)

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    create_invoice.assert_awaited_once()
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(910)
        payment = await repo.get_payment_by_external_id("ext-1")
    assert user is not None
    assert payment is not None
    assert payment.user_id == user.id
    assert payment.amount == 199


@pytest.mark.integration
async def test_buy_plan_handler_invalid_plan_alerts(session_pool, fake_bot):
    callback = SimpleNamespace(
        data="buy:unknown",
        from_user=SimpleNamespace(id=911, username="buyer"),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.integration
async def test_buy_plan_handler_uses_bot_when_no_message(session_pool, fake_bot, monkeypatch):
    callback = SimpleNamespace(
        data="buy:3m",
        from_user=SimpleNamespace(id=912, username="buyer"),
        message=None,
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        buy,
        "create_invoice",
        AsyncMock(return_value={"invoice_id": "ext-3", "bot_invoice_url": "https://pay.example/3"}),
    )

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    fake_bot.send_message.assert_awaited_once()


@pytest.mark.unit
def test_crypto_minor_units_rounds_half_up():
    assert buy._crypto_minor_units("1.995") == 200
    assert buy._crypto_minor_units("1.994") == 199
