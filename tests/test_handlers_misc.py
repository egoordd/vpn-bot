from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import instructions, subscription, support
from database.repository import Repository


@pytest.mark.unit
async def test_instructions_handler_edits_caption_for_photo_message():
    message = SimpleNamespace(photo=[object()], edit_caption=AsyncMock(), edit_text=AsyncMock())
    callback = SimpleNamespace(message=message, answer=AsyncMock())

    await instructions.instructions_handler(callback)

    message.edit_caption.assert_awaited_once()
    message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_once()


@pytest.mark.unit
async def test_support_handler_edits_text(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_USERNAME", "helpdesk")
    message = SimpleNamespace(photo=None, edit_caption=AsyncMock(), edit_text=AsyncMock())
    callback = SimpleNamespace(message=message, answer=AsyncMock())

    await support.support_handler(callback)

    message.edit_text.assert_awaited_once()
    assert "@helpdesk" in message.edit_text.await_args.args[0]
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
    assert "\u043d\u0435\u0442 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438" in message.edit_text.await_args.args[0]
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
