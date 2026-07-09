from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import start
from database.repository import Repository


@pytest.mark.integration
async def test_start_handler_gets_or_creates_user_and_sends_menu(session_pool, fake_bot):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=920, username="starter"),
        chat=SimpleNamespace(id=920),
        bot=fake_bot,
    )

    await start.start_handler(message, session_pool)

    fake_bot.send_photo.assert_awaited_once()
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

    text, keyboard, has_subscription = await start._menu_state(session_pool, 921, "active")

    assert has_subscription is True
    assert "Профиль" in text
    assert "Активных подписок" in text
    # Main menu: buy first, and "Мои подписки" present when a subscription is active
    assert keyboard.inline_keyboard[0][0].callback_data == "buy_menu"
    cbs = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert "my_subs" in cbs


@pytest.mark.integration
async def test_menu_state_shows_trial_button_for_new_user(session_pool):
    text, keyboard, has_subscription = await start._menu_state(session_pool, 924, "newbie")

    assert has_subscription is False
    assert "пробный период" in text.lower()
    cbs = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert cbs[0] == "activate_trial"  # trial button is first
    assert "my_subs" not in cbs
    # no silent auto-grant: the user still has no subscription
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(924)
        assert await Repository(session).get_latest_subscription(user.id) is None


@pytest.mark.integration
async def test_activate_trial_handler_grants_and_refreshes(session_pool, monkeypatch):
    async def fake_activate(*, session, user_id, plan, **kwargs):
        repo = Repository(session)
        return await repo.create_subscription(
            user_id=user_id, plan="trial", tier="trial",
            panel_username=f"tg_{user_id}", sub_token="t",
            subscription_url="https://sub.example/api/sub/t",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=3),
            is_active=True,
        )

    monkeypatch.setattr(start, "activate_panel_subscription", fake_activate)

    async def fake_show(callback, text, keyboard):
        return None

    monkeypatch.setattr(start, "show_screen", fake_show)
    callback = SimpleNamespace(
        data="activate_trial",
        from_user=SimpleNamespace(id=925, username="newbie", full_name="New"),
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )

    await start.activate_trial_handler(callback, session_pool)

    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(925)
        sub = await Repository(session).get_active_subscription(user.id)
    assert sub is not None and sub.plan == "trial"
    callback.answer.assert_awaited()


@pytest.mark.integration
async def test_activate_trial_handler_blocks_when_already_used(session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=926, username="repeat")
        await repo.create_subscription(
            user_id=user.id, plan="trial", tier="trial", panel_username="tg_926",
            sub_token="t", subscription_url="https://sub.example/api/sub/t",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=3), is_active=True,
        )
    activate = AsyncMock()
    monkeypatch.setattr(start, "activate_panel_subscription", activate)
    callback = SimpleNamespace(
        data="activate_trial",
        from_user=SimpleNamespace(id=926, username="repeat", full_name="R"),
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )

    await start.activate_trial_handler(callback, session_pool)

    activate.assert_not_awaited()  # already had a trial


@pytest.mark.unit
def test_start_aware_and_msk_formatting():
    naive = datetime(2026, 1, 1, 12, 0, 0)

    assert start._aware(naive).tzinfo == timezone.utc
    assert start._format_msk(naive) == "01 января 2026 года, 15:00 (МСК)"
    assert start._format_gb(None) == "∞"
    assert start._format_gb(10 * 1024 ** 3) == "10"
    assert start._format_gb(int(1.5 * 1024 ** 3)) == "1.5"


@pytest.mark.integration
async def test_start_handler_attaches_referrer_from_deep_link(session_pool, fake_bot):
    async with session_pool() as session:
        referrer = await Repository(session).create_user(telegram_id=921, username="ref")

    message = SimpleNamespace(
        text=f"/start ref_{referrer.ref_code}",
        from_user=SimpleNamespace(id=922, username="referee"),
        chat=SimpleNamespace(id=922),
        bot=fake_bot,
    )

    await start.start_handler(message, session_pool)

    async with session_pool() as session:
        referee = await Repository(session).get_user_by_telegram_id(922)
    assert referee is not None
    assert referee.referrer_id == referrer.id


@pytest.mark.integration
async def test_start_handler_ignores_bad_ref_code(session_pool, fake_bot):
    message = SimpleNamespace(
        text="/start ref_nonexistent",
        from_user=SimpleNamespace(id=923, username="referee2"),
        chat=SimpleNamespace(id=923),
        bot=fake_bot,
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


