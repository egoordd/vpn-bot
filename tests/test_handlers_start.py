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

    assert "Профиль" in text
    assert "Активных подписок" in text
    # Main menu: buy first, and "Мои подписки" present when a subscription is active
    assert keyboard.inline_keyboard[0][0].callback_data == "buy_menu"
    cbs = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert "my_subs" in cbs


@pytest.mark.integration
async def test_menu_state_does_not_auto_activate_trial_without_explicit_panel_client(session_pool):
    text, keyboard = await start._menu_state(session_pool, 924, "no_trial")

    assert "Активной подписки нет" in text
    cbs = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "my_subs" not in cbs
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(924)
        assert await Repository(session).get_latest_subscription(user.id) is None


@pytest.mark.integration
async def test_menu_state_auto_activates_trial_when_panel_client_is_available(session_pool):
    text, keyboard = await start._menu_state(session_pool, 922, "trial", panel_client=FakePanelClient())

    assert "Активных подписок" in text
    assert keyboard.inline_keyboard[0][0].callback_data == "buy_menu"
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(922)
        subscription = await repo.get_active_subscription(user.id)
    assert subscription.plan == "trial"
    assert subscription.subscription_url == "https://sub.example/api/sub/trial-short"


@pytest.mark.unit
def test_start_aware_and_msk_formatting():
    naive = datetime(2026, 1, 1, 12, 0, 0)

    assert start._aware(naive).tzinfo == timezone.utc
    assert start._format_msk(naive) == "01 января 2026 года, 15:00 (МСК)"
    assert start._format_gb(None) == "∞"
    assert start._format_gb(10 * 1024 ** 3) == "10"
    assert start._format_gb(int(1.5 * 1024 ** 3)) == "1.5"


@pytest.mark.integration
async def test_start_handler_attaches_referrer_from_deep_link(session_pool):
    async with session_pool() as session:
        referrer = await Repository(session).create_user(telegram_id=921, username="ref")

    message = SimpleNamespace(
        text=f"/start ref_{referrer.ref_code}",
        from_user=SimpleNamespace(id=922, username="referee"),
        answer_photo=AsyncMock(),
    )

    await start.start_handler(message, session_pool)

    async with session_pool() as session:
        referee = await Repository(session).get_user_by_telegram_id(922)
    assert referee is not None
    assert referee.referrer_id == referrer.id


@pytest.mark.integration
async def test_start_handler_ignores_bad_ref_code(session_pool):
    message = SimpleNamespace(
        text="/start ref_nonexistent",
        from_user=SimpleNamespace(id=923, username="referee2"),
        answer_photo=AsyncMock(),
    )

    await start.start_handler(message, session_pool)

    async with session_pool() as session:
        referee = await Repository(session).get_user_by_telegram_id(923)
    assert referee is not None
    assert referee.referrer_id is None


@pytest.mark.integration
async def test_my_subs_handler_lists_cards(session_pool):
    from datetime import datetime, timedelta, timezone

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=940, username="subs")
        await repo.create_subscription(
            user.id, "standard_1m", datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=10), True, tier="standard",
        )

    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="my_subs",
        from_user=SimpleNamespace(id=940, username="subs"),
        message=message,
        answer=AsyncMock(),
    )

    await start.my_subs_handler(callback, session_pool)

    text = message.edit_text.await_args.args[0]
    assert "Мои подписки" in text
    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "connect_device"


@pytest.mark.integration
async def test_maybe_grant_trial_activates_for_new_user(session_pool, monkeypatch):
    activate = AsyncMock()
    monkeypatch.setattr(start, "activate_panel_subscription", activate)
    message = SimpleNamespace(from_user=SimpleNamespace(id=980, username="newbie"))

    await start._maybe_grant_trial(session_pool, message)

    activate.assert_awaited_once()
    assert activate.await_args.kwargs["plan"] == "trial"


@pytest.mark.integration
async def test_maybe_grant_trial_skips_user_with_subscription(session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=981, username="returning")
        await repo.create_subscription(
            user_id=user.id, plan="standard_1m", tier="standard",
            panel_username="tg_981", sub_token="tok",
            subscription_url="https://sub.example/sub/tok",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )
    activate = AsyncMock()
    monkeypatch.setattr(start, "activate_panel_subscription", activate)
    message = SimpleNamespace(from_user=SimpleNamespace(id=981, username="returning"))

    await start._maybe_grant_trial(session_pool, message)

    activate.assert_not_awaited()
