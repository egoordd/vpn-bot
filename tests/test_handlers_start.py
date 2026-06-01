from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import start
from database.repository import Repository


@pytest.mark.integration
async def test_start_handler_gets_or_creates_user_and_sends_menu(session_pool):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=920, username="starter"),
        answer_photo=AsyncMock(),
    )

    await start.start_handler(message, session_pool)

    message.answer_photo.assert_awaited_once()
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(920)
    assert user is not None
    assert user.username == "starter"


@pytest.mark.integration
async def test_menu_state_returns_active_subscription_menu(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=921)
        await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=1),
            True,
        )

    text, keyboard = await start._menu_state(session_pool, 921, "active")

    assert "\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430" in text
    assert keyboard.inline_keyboard[0][0].callback_data == "get_key"


@pytest.mark.unit
def test_start_aware_and_active_text():
    naive = datetime(2026, 1, 1, 12, 0, 0)

    assert start._aware(naive).tzinfo == timezone.utc
    assert "01.01.2026 12:00 UTC" in start._active_text(naive)
