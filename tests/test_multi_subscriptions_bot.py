"""Бот: «➕ Ещё одна подписка», лимит, оплата с целью и продление конкретной подписки."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import buy
from bot.handlers.start import _menu_state, _my_subs_text
from database.repository import Repository


async def _account(session_pool, telegram_id: int, slots: int):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=telegram_id, username=f"u{telegram_id}")
        rows = []
        for n in range(1, slots + 1):
            name = f"tg_{telegram_id}" if n == 1 else f"tg_{telegram_id}_s{n}"
            rows.append(
                await repo.create_subscription(
                    user_id=user.id, plan="standard_1m", tier="standard", panel_username=name,
                    started_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=10 + n), is_active=True,
                )
            )
        return user, rows


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def _callback(data: str, telegram_id: int):
    message = SimpleNamespace(photo=None, edit_text=AsyncMock(), answer=AsyncMock())
    return SimpleNamespace(
        data=data, from_user=SimpleNamespace(id=telegram_id, username=f"u{telegram_id}"),
        message=message, answer=AsyncMock(),
    )


@pytest.mark.integration
async def test_the_menu_offers_another_subscription_only_to_subscribers(session_pool):
    await _account(session_pool, 7201, 1)
    _, keyboard, _ = await _menu_state(session_pool, 7201, "u7201")
    assert "buy_extra" in _callbacks(keyboard)

    _, keyboard, _ = await _menu_state(session_pool, 7202, "nobody")
    assert "buy_extra" not in _callbacks(keyboard)


@pytest.mark.integration
async def test_the_menu_hides_the_button_at_five(session_pool):
    await _account(session_pool, 7203, 5)
    _, keyboard, _ = await _menu_state(session_pool, 7203, "u7203")
    assert "buy_extra" not in _callbacks(keyboard)


@pytest.mark.integration
async def test_another_subscription_offers_plans_marked_new(session_pool):
    await _account(session_pool, 7204, 1)
    callback = _callback("buy_extra", 7204)

    await buy.buy_extra_handler(callback, AsyncMock(), session_pool)

    callbacks = _callbacks(callback.message.edit_text.await_args.kwargs["reply_markup"])
    assert "buy:standard_1m@new" in callbacks
    assert "main_menu" in callbacks


@pytest.mark.integration
async def test_another_subscription_is_refused_at_the_limit(session_pool):
    await _account(session_pool, 7205, 5)
    callback = _callback("buy_extra", 7205)

    await buy.buy_extra_handler(callback, AsyncMock(), session_pool)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()

    pay = _callback("payyk:standard_1m@new", 7205)
    await buy.pay_yookassa_handler(pay, AsyncMock(), session_pool, AsyncMock())
    assert pay.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.integration
async def test_checkout_for_another_subscription_keeps_the_mark(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    await _account(session_pool, 7206, 1)
    callback = _callback("buy:standard_3m@new", 7206)

    await buy.buy_plan_handler(callback, fake_bot, session_pool)

    kwargs = callback.message.edit_text.await_args
    callbacks = _callbacks(kwargs.kwargs["reply_markup"])
    assert "payyk:standard_3m@new" in callbacks
    assert "buy_extra" in callbacks, "«Назад» ведёт к срокам этой же покупки"
    assert "Ещё одна подписка" in kwargs.args[0]


@pytest.mark.integration
async def test_the_invoice_for_another_subscription_carries_the_target(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(buy.settings, "YOOKASSA_RECEIPT_ENABLED", False)
    monkeypatch.setattr(
        buy.yookassa, "create_payment",
        AsyncMock(return_value={"id": "yk-extra-bot", "confirmation": {"confirmation_url": "https://yoomoney.ru/p"}}),
    )
    await _account(session_pool, 7207, 1)
    callback = _callback("payyk:standard_1m@new", 7207)

    await buy.pay_yookassa_handler(callback, fake_bot, session_pool, AsyncMock())

    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("yk-extra-bot")
    assert payment.invoice_payload.endswith(":t=new")


@pytest.mark.integration
async def test_renewing_a_chosen_subscription_names_it_in_the_durations(session_pool):
    _, rows = await _account(session_pool, 7208, 2)
    extra = rows[1]
    callback = _callback(f"renew_sub:{extra.id}", 7208)

    await buy.renew_sub_handler(callback, session_pool)

    callbacks = _callbacks(callback.message.edit_text.await_args.kwargs["reply_markup"])
    assert f"buy:standard_1m@{extra.id}" in callbacks


@pytest.mark.integration
async def test_several_subscriptions_are_numbered(session_pool):
    _, rows = await _account(session_pool, 7209, 2)

    text = _my_subs_text(list(reversed(rows)))

    assert text.index("Подписка 1 · основная") < text.index("Подписка 2")


@pytest.mark.integration
async def test_a_single_subscription_keeps_the_plain_title(session_pool):
    _, rows = await _account(session_pool, 7210, 1)
    assert "Подписка 1" not in _my_subs_text(rows)
