from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import buy
from database.repository import Repository


@pytest.mark.integration
async def test_buy_plan_handler_creates_invoice_and_payment(session_pool, fake_bot, monkeypatch):
    callback = SimpleNamespace(
        data="buy:standard_1m",
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
async def test_buy_plan_handler_premium_opens_region_picker(session_pool, fake_bot):
    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="buy:premium_1m",
        from_user=SimpleNamespace(id=913, username="buyer"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    message.edit_text.assert_awaited_once()
    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "buy_region:premium_1m:ams"
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_buy_region_handler_creates_premium_invoice_with_region(session_pool, fake_bot, monkeypatch):
    callback = SimpleNamespace(
        data="buy_region:premium_1m:ams",
        from_user=SimpleNamespace(id=914, username="premium"),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    create_invoice = AsyncMock(return_value={"invoice_id": "ext-premium", "pay_url": "https://pay.example/p"})
    monkeypatch.setattr(buy, "create_invoice", create_invoice)

    await buy.buy_region_handler(callback, fake_bot, session_pool)

    create_invoice.assert_awaited_once()
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(914)
        payment = await repo.get_payment_by_external_id("ext-premium")
    assert user is not None
    assert payment is not None
    assert payment.user_id == user.id
    assert payment.amount == 499
    assert payment.invoice_payload is not None
    assert payment.invoice_payload.startswith(f"unlock:{user.id}:premium_1m:ams:")


@pytest.mark.integration
async def test_buy_region_handler_invalid_region_alerts(session_pool, fake_bot):
    callback = SimpleNamespace(
        data="buy_region:premium_1m:missing",
        from_user=SimpleNamespace(id=915, username="premium"),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )

    await buy.buy_region_handler(callback, fake_bot, session_pool)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.integration
async def test_buy_plan_handler_uses_bot_when_no_message(session_pool, fake_bot, monkeypatch):
    callback = SimpleNamespace(
        data="buy:standard_3m",
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


@pytest.mark.integration
async def test_buy_tier_handler_shows_tier_plans():
    message = SimpleNamespace(photo=None, edit_text=AsyncMock(), edit_caption=AsyncMock())
    callback = SimpleNamespace(
        data="buy_tier:premium",
        from_user=SimpleNamespace(id=915, username="tier"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.buy_tier_handler(callback)

    message.edit_text.assert_awaited_once()
    text = message.edit_text.await_args.args[0]
    assert "Premium" in text
    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "buy:premium_1m"


@pytest.mark.integration
async def test_buy_tier_handler_rejects_unknown_tier():
    callback = SimpleNamespace(
        data="buy_tier:gold",
        from_user=SimpleNamespace(id=916, username="tier"),
        message=SimpleNamespace(photo=None, edit_text=AsyncMock(), edit_caption=AsyncMock()),
        answer=AsyncMock(),
    )

    await buy.buy_tier_handler(callback)

    assert callback.answer.await_args.kwargs["show_alert"] is True
