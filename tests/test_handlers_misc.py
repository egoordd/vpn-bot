from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import instructions, subscription, support
from database.repository import Repository


@pytest.mark.unit
async def test_instructions_handler_replaces_photo_message():
    # On a photo message, navigation deletes it and sends a fresh text screen,
    # so a QR/banner never stays stuck behind a text caption.
    message = SimpleNamespace(
        photo=[object()],
        delete=AsyncMock(),
        answer=AsyncMock(),
        edit_text=AsyncMock(),
    )
    callback = SimpleNamespace(message=message, answer=AsyncMock())

    await instructions.instructions_handler(callback)

    message.delete.assert_awaited_once()
    message.answer.assert_awaited_once()
    message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_once()


@pytest.mark.unit
async def test_support_handler_edits_text(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_BOT_USERNAME", "unlock_support_bot")
    message = SimpleNamespace(photo=None, edit_caption=AsyncMock(), edit_text=AsyncMock())
    callback = SimpleNamespace(
        message=message,
        answer=AsyncMock(),
        from_user=SimpleNamespace(id=700, username="sup"),
    )

    await support.support_handler(callback)

    message.edit_text.assert_awaited_once()
    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    urls = [b.url for row in keyboard.inline_keyboard for b in row if b.url]
    assert any("unlock_support_bot" in u for u in urls)
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_subscription_handler_no_subscription(session_pool):
    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=930, username="sub"),
        message=message,
        answer=AsyncMock(),
    )

    await subscription.subscription_handler(callback, session_pool)

    message.edit_text.assert_awaited_once()
    assert "не активна" in message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_subscription_handler_active_subscription(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=931)
        await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=1),
            True,
        )

    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=931, username="sub"),
        message=message,
        answer=AsyncMock(),
    )

    await subscription.subscription_handler(callback, session_pool)

    message.edit_text.assert_awaited_once()
    assert "\u0430\u043a\u0442\u0438\u0432\u043d\u0430" in message.edit_text.await_args.args[0]


@pytest.mark.integration
async def test_subscription_handler_panel_subscription_shows_limits_and_link(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=932)
        await repo.create_subscription(
            user_id=user.id,
            plan="trial",
            tier="trial",
            panel_username="tg_932",
            sub_token="short",
            subscription_url="https://sub.example/api/sub/short",
            traffic_limit_bytes=10 * 1024**3,
            traffic_used_bytes=1024**3,
            device_limit=1,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            is_active=True,
        )

    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=932, username="sub"),
        message=message,
        answer=AsyncMock(),
    )

    await subscription.subscription_handler(callback, session_pool)

    text = message.edit_text.await_args.args[0]
    assert "1 / 10 ГБ" in text
    assert "https://sub.example/api/sub/short" in text




_AMS_INBOUNDS = '{"ams": {"vless": ["VLESS Reality AMS"]}}'






@pytest.mark.unit
async def test_help_command_shows_connect_and_support():
    from bot.handlers import help as help_handler

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=700, username="h"),
        answer=AsyncMock(),
    )
    await help_handler.help_command(message)
    text = message.answer.await_args.args[0]
    assert "Как подключиться" in text
    assert "Поддержка" in text
    assert "700" in text


@pytest.mark.integration
async def test_topup_screen_warns_that_it_needs_crypto():
    """Topping up is crypto-only, and paying a CryptoBot invoice needs crypto
    already in that wallet. Five top-ups have been attempted since the method
    went live and none completed; one customer spent a day believing he had paid
    and had only been stuck at CryptoBot's password screen. Buying a tariff does
    take a card, so the screen has to say so before it hands out an invoice."""
    from bot.handlers import wallet as wallet_handlers

    shown: list[str] = []

    async def capture(callback, text, keyboard=None):
        shown.append(text)

    class _State:
        async def clear(self):
            pass

    callback = SimpleNamespace(data="topup_menu", answer=AsyncMock(),
                               message=SimpleNamespace(photo=None))
    original = wallet_handlers._edit_current_message
    wallet_handlers._edit_current_message = capture
    try:
        await wallet_handlers.topup_menu_handler(callback, _State())
    finally:
        wallet_handlers._edit_current_message = original

    body = shown[0]
    assert "криптовалютой" in body, "the requirement must be stated, not discovered"
    assert "картой" in body.lower(), "a card buyer needs to be sent somewhere that works"
    assert "Купить подписку" in body


@pytest.mark.unit
def test_crypto_payment_offers_a_browser_route():
    """The Telegram link works inside the app and breaks in a browser: Telegram
    asks to log in, wants the two-factor password, then loses the invoice it was
    carrying and the page closes with nothing paid. A customer hit exactly that
    and spent a day believing his 600 RUB had gone somewhere. CryptoBot also
    issues a plain web address that needs no Telegram login."""
    from bot.handlers import buy, wallet as wallet_handlers

    for keyboard in (
        buy._payment_keyboard("https://t.me/CryptoBot?start=IV1", "6.67",
                              "https://app.send.tg/invoices/IV1"),
        wallet_handlers._topup_payment_keyboard("https://t.me/CryptoBot?start=IV1", "6.67",
                                                "https://app.send.tg/invoices/IV1"),
    ):
        urls = [b.url for row in keyboard.inline_keyboard for b in row if b.url]
        assert any("t.me/CryptoBot" in u for u in urls)
        assert any("app.send.tg" in u for u in urls), "the browser route must be offered"


@pytest.mark.unit
def test_no_browser_button_when_cryptobot_gives_no_web_url():
    """A dead button is worse than a missing one."""
    from bot.handlers import buy

    keyboard = buy._payment_keyboard("https://t.me/CryptoBot?start=IV1", "6.67", None)
    urls = [b.url for row in keyboard.inline_keyboard for b in row if b.url]
    assert urls == ["https://t.me/CryptoBot?start=IV1"]
