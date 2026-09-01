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