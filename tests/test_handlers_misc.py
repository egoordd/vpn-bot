from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import instructions, locations, subscription, support
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
    monkeypatch.setattr(support.settings, "SUPPORT_USERNAME", "helpdesk")
    message = SimpleNamespace(photo=None, edit_caption=AsyncMock(), edit_text=AsyncMock())
    callback = SimpleNamespace(
        message=message,
        answer=AsyncMock(),
        from_user=SimpleNamespace(id=700, username="sup"),
    )

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


_AMS_INBOUNDS = '{"ams": {"vless": ["VLESS Reality AMS"]}}'


@pytest.mark.integration
async def test_locations_handler_shows_shared_locations_info(session_pool):
    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=934, username="loc"),
        message=message,
        answer=AsyncMock(),
    )

    await locations.locations_handler(callback, session_pool)

    text = message.edit_text.await_args.args[0]
    assert "США" in text and "Нидерланды" in text
    assert "приложении" in text


@pytest.mark.integration
async def test_set_location_handler_switches_static_region(session_pool, monkeypatch):
    import services.subscription as subscription_module

    monkeypatch.setattr(locations.settings, "MARZBAN_REGION_INBOUNDS", _AMS_INBOUNDS)
    monkeypatch.setattr(subscription_module.settings, "MARZBAN_REGION_INBOUNDS", _AMS_INBOUNDS)

    class FakeGateway:
        provider = "fake"

        async def modify_user(self, **kwargs):
            assert kwargs["inbounds"] == {"vless": ["VLESS Reality AMS"]}
            return SimpleNamespace(subscription_url="https://sub/ams", username="tg_935p", status="active")

    monkeypatch.setattr(subscription_module, "get_panel_gateway", lambda: FakeGateway())

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=935)
        subscription_row = await repo.create_subscription(
            user_id=user.id,
            plan="premium_1m",
            tier="premium",
            region=None,
            panel_username="tg_935p",
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
        refreshed = await Repository(session).get_subscription(subscription_row.id)

    assert refreshed.region == "ams"
    assert refreshed.subscription_url == "https://sub/ams"
    assert "Локация обновлена" in message.edit_text.await_args.args[0]
