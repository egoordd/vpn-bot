from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import wallet as wallet_handlers
from database.repository import Repository
from services import wallet
from services.promo import PROMO_BALANCE_BONUS


def _callback(data: str, telegram_id: int = 950, *, with_photo: bool = False):
    message = SimpleNamespace(
        photo=[object()] if with_photo else None,
        edit_text=AsyncMock(),
        edit_caption=AsyncMock(),
        answer=AsyncMock(),
    )
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=telegram_id, username="walletuser"),
        message=message,
        answer=AsyncMock(),
    )


def _state():
    return SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())


@pytest.mark.integration
async def test_wallet_handler_shows_balance_and_history(session_pool):
    callback = _callback("wallet", telegram_id=951)
    state = _state()
    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=951, username="walletuser")
        await wallet.deposit(session, user.id, 15000, description="Пополнение")

    await wallet_handlers.wallet_handler(callback, state, session_pool)

    state.clear.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()
    text = callback.message.edit_text.await_args.args[0]
    assert "150₽" in text
    assert "Пополнение" in text
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_wallet_handler_creates_user_when_missing(session_pool):
    callback = _callback("wallet", telegram_id=952)

    await wallet_handlers.wallet_handler(callback, _state(), session_pool)

    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(952)
    assert user is not None


@pytest.mark.integration
async def test_topup_handler_creates_invoice_and_pending_payment(session_pool, fake_bot, monkeypatch):
    callback = _callback("topup:15000", telegram_id=953)
    async def create_invoice(**kwargs):
        assert callback.answer.await_count == 1
        return {"invoice_id": "top-1", "pay_url": "https://pay.example/top"}

    create_invoice = AsyncMock(side_effect=create_invoice)
    monkeypatch.setattr(wallet_handlers, "create_invoice", create_invoice)

    await wallet_handlers.topup_handler(callback, fake_bot, session_pool)

    create_invoice.assert_awaited_once()
    sent_payload = create_invoice.await_args.kwargs["payload"]
    assert sent_payload.startswith("unlock_topup:")
    callback.message.answer.assert_awaited_once()
    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("top-1")
    assert payment is not None
    assert payment.status == "pending"
    assert payment.invoice_payload == sent_payload


@pytest.mark.integration
async def test_topup_handler_rejects_bad_amounts(session_pool, fake_bot):
    for data in ("topup:abc", "topup:100", "topup:999999999"):
        callback = _callback(data, telegram_id=954)
        await wallet_handlers.topup_handler(callback, fake_bot, session_pool)
        assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.integration
async def test_promo_message_credits_balance(session_pool):
    message = SimpleNamespace(
        text="WELCOME",
        from_user=SimpleNamespace(id=955, username="promouser"),
        answer=AsyncMock(),
    )
    state = _state()
    async with session_pool() as session:
        await Repository(session).create_promo_code(code="WELCOME", kind=PROMO_BALANCE_BONUS, value=5000)

    await wallet_handlers.promo_code_message_handler(message, state, session_pool)

    state.clear.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "+50₽" in text
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(955)
        balance = await Repository(session).get_balance(user.id)
    assert balance == 5000


@pytest.mark.integration
async def test_promo_message_reports_unknown_code(session_pool):
    message = SimpleNamespace(
        text="GHOST",
        from_user=SimpleNamespace(id=956, username="promouser"),
        answer=AsyncMock(),
    )
    state = _state()

    await wallet_handlers.promo_code_message_handler(message, state, session_pool)

    state.clear.assert_not_awaited()
    assert "нет" in message.answer.await_args.args[0].lower()


@pytest.mark.integration
async def test_referral_handler_shows_link_and_stats(session_pool, fake_bot):
    fake_bot.id = 42
    fake_bot.get_me = AsyncMock(return_value=SimpleNamespace(username="unlock_bot"))
    callback = _callback("referral", telegram_id=957)

    await wallet_handlers.referral_handler(callback, fake_bot, session_pool)

    text = callback.message.edit_text.await_args.args[0]
    assert "https://t.me/unlock_bot?start=ref_tg957" in text
    assert "20%" in text


@pytest.mark.integration
async def test_pay_with_balance_success(session_pool, monkeypatch):
    callback = _callback("paybal:standard_1m", telegram_id=958)
    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=958, username="payer")
        await wallet.deposit(session, user.id, 20000)

    from datetime import datetime, timedelta, timezone

    async def activate(**kwargs):
        assert callback.answer.await_count == 1
        return SimpleNamespace(
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            subscription_url="https://sub.example/sub/paidbal",
        )

    activate = AsyncMock(side_effect=activate)
    monkeypatch.setattr(wallet_handlers, "activate_panel_subscription", activate)
    monkeypatch.setattr(wallet_handlers, "is_panel_configured", lambda: True)

    await wallet_handlers.pay_with_balance_handler(callback, session_pool)

    activate.assert_awaited_once()
    callback.message.answer.assert_awaited_once()
    text = callback.message.answer.await_args.args[0]
    assert "Ссылка-подписка" in text
    async with session_pool() as session:
        balance = await Repository(session).get_balance(user.id)
    assert balance == 20000 - 14900


@pytest.mark.integration
async def test_pay_with_balance_insufficient_alerts(session_pool, monkeypatch):
    callback = _callback("paybal:standard_1m", telegram_id=959)
    monkeypatch.setattr(wallet_handlers, "is_panel_configured", lambda: True)

    await wallet_handlers.pay_with_balance_handler(callback, session_pool)

    assert callback.answer.await_args.kwargs["show_alert"] is True
    assert "Не хватает" in callback.answer.await_args.args[0]


@pytest.mark.integration
async def test_pay_with_balance_refunds_on_panel_failure(session_pool, monkeypatch):
    callback = _callback("paybal:standard_1m", telegram_id=960)
    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=960, username="payer")
        await wallet.deposit(session, user.id, 14900)

    activate = AsyncMock(side_effect=RuntimeError("panel down"))
    monkeypatch.setattr(wallet_handlers, "activate_panel_subscription", activate)
    monkeypatch.setattr(wallet_handlers, "is_panel_configured", lambda: True)

    await wallet_handlers.pay_with_balance_handler(callback, session_pool)

    callback.answer.assert_awaited_once_with()
    callback.message.answer.assert_awaited_once()
    assert "вернулись" in callback.message.answer.await_args.args[0]
    async with session_pool() as session:
        repo = Repository(session)
        balance = await repo.get_balance(user.id)
        entries = await repo.list_wallet_transactions(user.id)
    assert balance == 14900
    kinds = [entry.kind for entry in entries]
    assert wallet.KIND_REFUND in kinds
    assert wallet.KIND_SPEND in kinds








@pytest.mark.integration
async def test_topup_custom_sets_state_and_prompts(session_pool):
    from bot.handlers.wallet import TopupInput

    callback = _callback("topup_custom", telegram_id=962)
    state = SimpleNamespace(set_state=AsyncMock(), clear=AsyncMock())

    await wallet_handlers.topup_custom_handler(callback, state)

    state.set_state.assert_awaited_once_with(TopupInput.amount)
    callback.message.edit_text.assert_awaited_once()


@pytest.mark.integration
async def test_topup_amount_message_creates_invoice(session_pool, fake_bot, monkeypatch):
    create_invoice = AsyncMock(return_value={"invoice_id": "cust-1", "pay_url": "https://pay.example/c"})
    monkeypatch.setattr(wallet_handlers, "create_invoice", create_invoice)
    message = SimpleNamespace(
        text="250",
        from_user=SimpleNamespace(id=963, username="custom"),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock())

    await wallet_handlers.topup_amount_message_handler(message, state, fake_bot, session_pool)

    state.clear.assert_awaited_once()
    create_invoice.assert_awaited_once()
    message.answer.assert_awaited_once()
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(963)
        payment = await Repository(session).get_payment_by_external_id("cust-1")
    assert payment is not None
    assert payment.invoice_payload.startswith("unlock_topup:")


@pytest.mark.integration
async def test_topup_amount_message_rejects_bad_input(session_pool, fake_bot):
    state = SimpleNamespace(clear=AsyncMock())
    for raw in ("abc", "10", "999999"):
        message = SimpleNamespace(
            text=raw,
            from_user=SimpleNamespace(id=964, username="custom"),
            answer=AsyncMock(),
        )
        await wallet_handlers.topup_amount_message_handler(message, state, fake_bot, session_pool)
        message.answer.assert_awaited_once()
    state.clear.assert_not_awaited()
