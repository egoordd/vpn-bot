from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import buy
from database.repository import Repository


@pytest.mark.integration
async def test_buy_plan_checkout_back_goes_to_tier_plans(session_pool, fake_bot, monkeypatch):
    # «Назад» from checkout = one step back (this tier's plan list), not buy_menu.
    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="buy:standard_1m",
        from_user=SimpleNamespace(id=920, username="nav"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "buy_tier:standard" in callbacks
    assert "buy_menu" not in callbacks


@pytest.mark.integration
async def test_buy_plan_standard_shows_card_first_when_yookassa_configured(session_pool, fake_bot, monkeypatch):
    # Card (YooKassa) is the only rail left, and must be the first button.
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
async def test_renew_goes_straight_to_durations_for_a_single_subscription(session_pool):
    """One tier means the «какую продлить» screen offers exactly one thing, and
    a screen with one option is a tap that answers nothing."""
    from datetime import datetime, timedelta, timezone

    from database.repository import Repository

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=972, username="onesub")
        await repo.create_subscription(
            user_id=user.id, plan="standard_1m", tier="standard",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=10), is_active=True,
        )

    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="renew_menu",
        from_user=SimpleNamespace(id=972, username="onesub"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.renew_menu_handler(callback, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert any(cb.startswith("buy:standard_") for cb in callbacks), "должны быть сроки, а не выбор подписки"
    assert not any(cb.startswith("renew_sub:") for cb in callbacks)
    # «Назад» must leave, not loop back into a screen that forwards here again.
    assert "main_menu" in callbacks
    assert "renew_menu" not in callbacks


@pytest.mark.integration
async def test_renew_still_asks_which_one_when_there_are_several(session_pool):
    from datetime import datetime, timedelta, timezone

    from database.repository import Repository

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=973, username="twosubs")
        for days in (10, 40):
            await repo.create_subscription(
                user_id=user.id, plan="standard_1m", tier="standard",
                started_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=days), is_active=True,
            )

    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="renew_menu",
        from_user=SimpleNamespace(id=973, username="twosubs"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.renew_menu_handler(callback, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    buttons = [b for row in keyboard.inline_keyboard for b in row]
    assert sum(b.callback_data.startswith("renew_sub:") for b in buttons) == 2
    # ...and they must be told apart by something real, not by a tier that no
    # longer has an alternative.
    labels = [b.text for b in buttons if b.callback_data.startswith("renew_sub:")]
    assert len(set(labels)) == 2, f"кнопки неразличимы: {labels}"
    assert not any("Обычный" in t for t in labels)


@pytest.mark.integration
async def test_renew_sub_opens_the_duration_list(session_pool):
    """Pressing «Продлить» on a subscription must reach the duration options.

    The Premium removal dropped the region argument at the call site but left it
    required on the keyboard, so every renewal raised TypeError — the renewal
    path had no test to catch it, and renewals are revenue.
    """
    from datetime import datetime, timedelta, timezone

    from database.repository import Repository

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=971, username="renewsub")
        sub = await repo.create_subscription(
            user_id=user.id, plan="standard_1m", tier="standard",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=10), is_active=True,
        )
        sub_id = sub.id

    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data=f"renew_sub:{sub_id}",
        from_user=SimpleNamespace(id=971, username="renewsub"),
        message=message,
        answer=AsyncMock(),
    )

    await buy.renew_sub_handler(callback, session_pool)

    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert any(cb.startswith("buy:standard_") for cb in callbacks)
    assert "renew_menu" in callbacks  # «Назад» stays reachable


@pytest.mark.unit
def test_renew_durations_offer_only_callbacks_something_handles():
    """A button nobody handles is a dead end for whoever presses it."""
    from bot.keyboards.main_menu import renew_durations_keyboard

    keyboard = renew_durations_keyboard("standard")
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]

    assert callbacks, "renewal must offer at least one duration"
    assert not any(cb.startswith("buy_region:") for cb in callbacks)


@pytest.mark.integration
async def test_yookassa_pay_keyboard_email_edit_button():
    kb = buy._yookassa_pay_keyboard(
        "https://pay.example", 149, plan="standard_1m", email_editable=True
    )
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "ykemail:standard_1m" in callbacks

    kb_no_email = buy._yookassa_pay_keyboard("https://pay.example", 149, plan="standard_1m")
    callbacks = [btn.callback_data for row in kb_no_email.inline_keyboard for btn in row]
    assert not any((cb or "").startswith("ykemail:") for cb in callbacks)


@pytest.mark.integration
async def test_yookassa_change_email_flow_reissues_invoice(session_pool, fake_bot, monkeypatch):
    # Tap «Изменить email» → send a corrected address → email saved and a NEW
    # invoice is created with it.
    from services import yookassa as yk

    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=921, username="typo")
        await Repository(session).update_user(user.id, email="tpyo@mail.ru")

    state_data: dict = {}
    state = SimpleNamespace(
        set_state=AsyncMock(),
        update_data=AsyncMock(side_effect=lambda **kw: state_data.update(kw)),
        get_data=AsyncMock(side_effect=lambda: dict(state_data)),
        clear=AsyncMock(),
    )
    message_ns = SimpleNamespace(photo=None, edit_text=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(
        data="ykemail:standard_1m",
        from_user=SimpleNamespace(id=921, username="typo"),
        message=message_ns,
        answer=AsyncMock(),
    )

    await buy.yookassa_change_email_handler(callback, fake_bot, state)

    state.set_state.assert_awaited_once()
    assert state_data == {"plan": "standard_1m"}

    created: dict = {}

    async def fake_create_payment(**kwargs):
        created.update(kwargs)
        return {"id": "yk-fix-1", "confirmation": {"confirmation_url": "https://pay.example/fix"}}

    monkeypatch.setattr(yk, "create_payment", fake_create_payment)

    incoming = SimpleNamespace(
        text="fixed@mail.ru",
        from_user=SimpleNamespace(id=921, username="typo"),
        answer=AsyncMock(),
    )
    await buy.yookassa_email_message_handler(incoming, state, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_user_by_telegram_id(921)
        assert refreshed.email == "fixed@mail.ru"
    assert created.get("receipt_email") == "fixed@mail.ru"
    incoming.answer.assert_awaited()
