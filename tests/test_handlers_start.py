from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import start
from database.repository import Repository
from services.panel_client import PanelUsage, PanelUser, RemnawaveNotFoundError


class FakePanelClient:
    async def get_user(self, username: str) -> PanelUser:
        raise RemnawaveNotFoundError("missing")

    async def create_user(self, **kwargs) -> PanelUser:
        return PanelUser(
            uuid="uuid",
            username=str(kwargs["username"]),
            short_uuid="trial-short",
            subscription_url="https://sub.example/api/sub/trial-short",
            status="ACTIVE",
            expire_at="2026-07-03T00:00:00Z",
            traffic_limit_bytes=10 * 1024**3,
            traffic_limit_strategy="NO_RESET",
            hwid_device_limit=1,
            usage=PanelUsage(used_traffic_bytes=0, lifetime_used_traffic_bytes=0),
        )


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
    assert keyboard.inline_keyboard[0][0].callback_data == "connect_device"


@pytest.mark.integration
async def test_menu_state_auto_activates_trial_when_panel_client_is_available(session_pool):
    text, keyboard = await start._menu_state(session_pool, 922, "trial", panel_client=FakePanelClient())

    assert "\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430" in text
    assert keyboard.inline_keyboard[0][0].callback_data == "connect_device"
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(922)
        subscription = await repo.get_active_subscription(user.id)
    assert subscription.plan == "trial"
    assert subscription.subscription_url == "https://sub.example/api/sub/trial-short"


@pytest.mark.unit
def test_start_aware_and_active_text():
    naive = datetime(2026, 1, 1, 12, 0, 0)

    assert start._aware(naive).tzinfo == timezone.utc
    assert "01.01.2026 12:00 UTC" in start._active_text(naive)
