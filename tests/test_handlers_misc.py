from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import instructions, locations, subscription, support
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
    assert "1.0 \u0413\u0411 / 10.0 \u0413\u0411" in text
    assert "https://sub.example/api/sub/short" in text


@pytest.mark.integration
async def test_locations_handler_standard_subscription_prompts_premium(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=933)
        await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )

    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=933, username="loc"),
        message=message,
        answer=AsyncMock(),
    )

    await locations.locations_handler(callback, session_pool)

    text = message.edit_text.await_args.args[0]
    assert "Premium" in text
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_locations_handler_shows_current_premium_region(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=934)
        node = await repo.create_node(
            tier="premium",
            capacity=2,
            region="fra",
            provider="manual",
            ip_address="203.0.113.34",
            panel_node_id="panel-fra",
            current_users=1,
        )
        await repo.create_subscription(
            user_id=user.id,
            plan="premium_1m",
            tier="premium",
            node_ids=[node.panel_node_id],
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )

    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=934, username="loc"),
        message=message,
        answer=AsyncMock(),
    )

    await locations.locations_handler(callback, session_pool)

    text = message.edit_text.await_args.args[0]
    assert "Германия, Франкфурт" in text
    keyboard = message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[1][0].text.startswith("✅")


@pytest.mark.integration
async def test_set_location_handler_moves_premium_subscription_to_available_node(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=935)
        old_node = await repo.create_node(
            tier="premium",
            capacity=2,
            region="fra",
            provider="manual",
            ip_address="203.0.113.35",
            panel_node_id="panel-fra",
            current_users=1,
        )
        target_node = await repo.create_node(
            tier="premium",
            capacity=2,
            region="ams",
            provider="manual",
            ip_address="203.0.113.36",
            panel_node_id="panel-ams",
            current_users=0,
        )
        subscription_row = await repo.create_subscription(
            user_id=user.id,
            plan="premium_1m",
            tier="premium",
            node_ids=[old_node.panel_node_id],
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )

    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="set_location:ams",
        from_user=SimpleNamespace(id=935, username="loc"),
        message=message,
        answer=AsyncMock(),
    )

    await locations.set_location_handler(callback, session_pool)

    async with session_pool() as session:
        repo = Repository(session)
        refreshed_subscription = await repo.get_subscription(subscription_row.id)
        refreshed_old = await repo.get_node(old_node.id)
        refreshed_target = await repo.get_node(target_node.id)

    assert refreshed_subscription.node_ids == ["panel-ams"]
    assert refreshed_old.current_users == 0
    assert refreshed_target.current_users == 1
    assert "Локация обновлена" in message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once()
