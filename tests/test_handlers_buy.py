from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import buy
from database.repository import Repository


@pytest.mark.integration
async def test_buy_plan_standard_shows_checkout_with_balance_option(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy, "is_cryptobot_configured", lambda: False)
    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="buy:standard_1m",
        from_user=SimpleNamespace(id=910, username="buyer"),
        message=message,
        answer=AsyncMock(),
    )
    async with session_pool() as session:
        user = await Repository(session).get_or_create_user(telegram_id=910, username="buyer")
        from services import wallet

        await wallet.deposit(session, user.id, 100000)

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    message.edit_text.assert_awaited_once()
    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "paybal:standard_1m"
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_buy_plan_standard_without_balance_offers_topup(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy, "is_cryptobot_configured", lambda: False)
    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="buy:standard_1m",
        from_user=SimpleNamespace(id=917, username="poor"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "topup_menu" in callbacks
    assert not any(cb.startswith("paybal:") for cb in callbacks)


@pytest.mark.integration
async def test_buy_plan_standard_shows_card_first_when_yookassa_configured(session_pool, fake_bot, monkeypatch):
    # Card (YooKassa) must be the FIRST button; crypto off, balance zero.
    monkeypatch.setattr(buy, "is_cryptobot_configured", lambda: False)
    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="buy:standard_1m",
        from_user=SimpleNamespace(id=931, username="ykuser"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    first_button = keyboard.inline_keyboard[0][0]
    assert first_button.callback_data == "payyk:standard_1m"
    assert first_button.text == "💳 Оплатить картой"


@pytest.mark.integration
async def test_pay_yookassa_handler_creates_payment_when_receipts_off(session_pool, fake_bot, monkeypatch):
    from unittest.mock import AsyncMock as _AsyncMock

    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(buy.settings, "YOOKASSA_RECEIPT_ENABLED", False)
    monkeypatch.setattr(
        buy.yookassa,
        "create_payment",
        _AsyncMock(return_value={"id": "yk-buy-1", "confirmation": {"confirmation_url": "https://yoomoney.ru/pay/z"}}),
    )
    sent = {}

    async def send(callback, bot, text, reply_markup=None):
        sent["markup"] = reply_markup

    monkeypatch.setattr(buy, "_send_callback_message", send)

    callback = SimpleNamespace(
        data="payyk:standard_1m",
        from_user=SimpleNamespace(id=932, username="ykbuyer"),
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )

    await buy.pay_yookassa_handler(callback, fake_bot, session_pool, _AsyncMock())

    urls = [btn.url for row in sent["markup"].inline_keyboard for btn in row if getattr(btn, "url", None)]
    assert "https://yoomoney.ru/pay/z" in urls
    async with session_pool() as session:
        from database.repository import Repository

        user = await Repository(session).get_user_by_telegram_id(932)
        payment = await Repository(session).get_payment_by_external_id("yk-buy-1")
    assert payment is not None
    assert payment.provider == "yookassa"
    assert payment.user_id == user.id


@pytest.mark.integration
async def test_pay_yookassa_skips_email_prompt_in_on_page_mode(session_pool, fake_bot, monkeypatch):
    from unittest.mock import AsyncMock as _AsyncMock

    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(buy.settings, "YOOKASSA_RECEIPT_ENABLED", True)
    monkeypatch.setattr(buy.settings, "YOOKASSA_COLLECT_EMAIL_ON_PAGE", True)
    create = _AsyncMock(
        return_value={"id": "yk-onpage-1", "confirmation": {"confirmation_url": "https://yoomoney.ru/pay/op"}}
    )
    monkeypatch.setattr(buy.yookassa, "create_payment", create)
    sent = {}

    async def send(callback, bot, text, reply_markup=None):
        sent["markup"] = reply_markup

    monkeypatch.setattr(buy, "_send_callback_message", send)
    state = _AsyncMock()
    callback = SimpleNamespace(
        data="payyk:standard_1m",
        from_user=SimpleNamespace(id=945, username="onpage"),
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )

    await buy.pay_yookassa_handler(callback, fake_bot, session_pool, state)

    state.set_state.assert_not_awaited()  # no email prompt
    create.assert_awaited_once()
    urls = [btn.url for row in sent["markup"].inline_keyboard for btn in row if getattr(btn, "url", None)]
    assert "https://yoomoney.ru/pay/op" in urls


@pytest.mark.integration
async def test_pay_yookassa_asks_email_when_receipts_on(session_pool, fake_bot, monkeypatch):
    from unittest.mock import AsyncMock as _AsyncMock

    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(buy.settings, "YOOKASSA_RECEIPT_ENABLED", True)
    create = _AsyncMock()
    monkeypatch.setattr(buy.yookassa, "create_payment", create)
    prompt = {}

    async def send(callback, bot, text, reply_markup=None):
        prompt["text"] = text

    monkeypatch.setattr(buy, "_send_callback_message", send)
    state = _AsyncMock()
    callback = SimpleNamespace(
        data="payyk:standard_1m",
        from_user=SimpleNamespace(id=940, username="needsmail"),
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )

    await buy.pay_yookassa_handler(callback, fake_bot, session_pool, state)

    state.set_state.assert_awaited_once()
    create.assert_not_awaited()
    assert "email" in prompt["text"].lower()


@pytest.mark.integration
async def test_yookassa_email_message_stores_and_creates(session_pool, fake_bot, monkeypatch):
    from unittest.mock import AsyncMock as _AsyncMock

    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(buy.settings, "YOOKASSA_RECEIPT_ENABLED", True)
    create = _AsyncMock(
        return_value={"id": "yk-em-1", "confirmation": {"confirmation_url": "https://yoomoney.ru/pay/e"}}
    )
    monkeypatch.setattr(buy.yookassa, "create_payment", create)
    state = _AsyncMock()
    state.get_data = _AsyncMock(return_value={"plan": "standard_1m", "region": None})
    message = SimpleNamespace(
        text="buyer@mail.ru", from_user=SimpleNamespace(id=941, username="em"), answer=AsyncMock()
    )

    await buy.yookassa_email_message_handler(message, state, session_pool)

    assert create.await_args.kwargs["receipt_email"] == "buyer@mail.ru"
    async with session_pool() as session:
        from database.repository import Repository

        user = await Repository(session).get_user_by_telegram_id(941)
    assert user.email == "buyer@mail.ru"


@pytest.mark.integration
async def test_yookassa_email_message_rejects_bad_email(session_pool, monkeypatch):
    from unittest.mock import AsyncMock as _AsyncMock

    state = _AsyncMock()
    message = SimpleNamespace(
        text="not-an-email", from_user=SimpleNamespace(id=942, username="bad"), answer=AsyncMock()
    )

    await buy.yookassa_email_message_handler(message, state, session_pool)

    message.answer.assert_awaited()
    state.clear.assert_not_awaited()


@pytest.mark.integration
async def test_pay_crypto_handler_creates_invoice_and_payment(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy, "is_cryptobot_configured", lambda: True)
    async def create_invoice(**kwargs):
        assert callback.answer.await_count == 1
        return {"invoice_id": "ext-1", "pay_url": "https://pay.example"}

    create_invoice = AsyncMock(side_effect=create_invoice)
    monkeypatch.setattr(buy, "create_invoice", create_invoice)
    callback = SimpleNamespace(
        data="paycrypto:standard_1m",
        from_user=SimpleNamespace(id=910, username="buyer"),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )

    await buy.pay_crypto_handler(callback, fake_bot, session_pool)

    create_invoice.assert_awaited_once()
    callback.message.answer.assert_awaited_once()
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(910)
        payment = await repo.get_payment_by_external_id("ext-1")
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
async def test_premium_entry_points_show_coming_soon(session_pool, fake_bot):
    for data in ("buy_tier:premium", "buy:premium_1m", "buy_region:premium_1m:ams"):
        message = SimpleNamespace(photo=None, edit_text=AsyncMock())
        callback = SimpleNamespace(
            data=data,
            from_user=SimpleNamespace(id=913, username="buyer"),
            message=message,
            answer=AsyncMock(),
        )
        if data == "buy_tier:premium":
            await buy.buy_tier_handler(callback)
        elif data.startswith("buy_region:"):
            await buy.buy_region_handler(callback, fake_bot, session_pool)
        else:
            await buy.buy_plan_handler(callback, fake_bot, session_pool)

        text = message.edit_text.await_args.args[0]
        assert "скоро" in text.lower()


@pytest.mark.integration
async def test_pay_crypto_handler_uses_bot_when_no_message(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy, "is_cryptobot_configured", lambda: True)
    callback = SimpleNamespace(
        data="paycrypto:standard_3m",
        from_user=SimpleNamespace(id=912, username="buyer"),
        message=None,
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        buy,
        "create_invoice",
        AsyncMock(return_value={"invoice_id": "ext-3", "bot_invoice_url": "https://pay.example/3"}),
    )

    await buy.pay_crypto_handler(callback, fake_bot, session_pool)

    fake_bot.send_message.assert_awaited_once()


@pytest.mark.unit
def test_crypto_minor_units_rounds_half_up():
    assert buy._crypto_minor_units("1.995") == 200
    assert buy._crypto_minor_units("1.994") == 199


@pytest.mark.integration
async def test_buy_tier_handler_shows_standard_durations():
    message = SimpleNamespace(photo=None, edit_text=AsyncMock(), edit_caption=AsyncMock())
    callback = SimpleNamespace(
        data="buy_tier:standard",
        from_user=SimpleNamespace(id=915, username="tier"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.buy_tier_handler(callback)

    message.edit_text.assert_awaited_once()
    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "buy:standard_1m"


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


@pytest.mark.integration
async def test_renew_menu_lists_active_subscriptions(session_pool):
    from datetime import datetime, timedelta, timezone

    from database.repository import Repository

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=970, username="renew")
        await repo.create_subscription(
            user_id=user.id, plan="standard_1m", tier="standard",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=10), is_active=True,
        )
        await repo.create_subscription(
            user_id=user.id, plan="premium_1m", tier="premium", region="ams",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=20), is_active=True,
        )

    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="renew_menu",
        from_user=SimpleNamespace(id=970, username="renew"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.renew_menu_handler(callback, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert sum(cb.startswith("renew_sub:") for cb in callbacks) == 2


@pytest.mark.integration
async def test_renew_sub_premium_keeps_region(session_pool):
    from datetime import datetime, timedelta, timezone

    from database.repository import Repository

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=971, username="renew")
        sub = await repo.create_subscription(
            user_id=user.id, plan="premium_1m", tier="premium", region="ams",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=20), is_active=True,
        )

    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data=f"renew_sub:{sub.id}",
        from_user=SimpleNamespace(id=971, username="renew"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.renew_sub_handler(callback, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    # premium renewal durations keep the region and route to buy_region (checkout)
    assert any(cb == "buy_region:premium_1m:ams" for cb in callbacks)
