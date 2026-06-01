from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.middlewares import subscription_check
from bot.middlewares.subscription_check import SubscriptionCheckMiddleware
from database.repository import Repository


@pytest.mark.unit
async def test_middleware_without_subscription_required_flag_passthrough():
    middleware = SubscriptionCheckMiddleware()
    handler = AsyncMock(return_value="handled")
    event = object()

    data = {"handler": SimpleNamespace(flags={})}
    result = await middleware(handler, event, data)

    assert result == "handled"
    handler.assert_awaited_once_with(event, data)


@pytest.mark.integration
async def test_middleware_with_active_subscription_passthrough(session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=800)

    middleware = SubscriptionCheckMiddleware()
    handler = AsyncMock(return_value="handled")
    monkeypatch.setattr(subscription_check, "check_subscription_active", AsyncMock(return_value=True))
    data = {
        "handler": SimpleNamespace(flags={"subscription_required": True}),
        "event_from_user": SimpleNamespace(id=800),
        "session_pool": session_pool,
    }

    result = await middleware(handler, object(), data)

    assert user.id
    assert result == "handled"
    handler.assert_awaited_once()


@pytest.mark.integration
async def test_middleware_callback_without_subscription_answers_alert(session_pool, monkeypatch):
    middleware = SubscriptionCheckMiddleware()
    handler = AsyncMock(return_value="handled")
    answer = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    callback = CallbackQuery(
        id="callback-id",
        from_user=User(id=801, is_bot=False, first_name="Alice"),
        chat_instance="chat-instance",
    )
    monkeypatch.setattr(subscription_check, "check_subscription_active", AsyncMock(return_value=False))
    data = {
        "handler": SimpleNamespace(flags={"subscription_required": True}),
        "event_from_user": SimpleNamespace(id=801),
        "session_pool": session_pool,
    }

    result = await middleware(handler, callback, data)

    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()
    assert answer.await_args.kwargs["show_alert"] is True


@pytest.mark.integration
async def test_middleware_message_without_subscription_answers(session_pool, monkeypatch):
    middleware = SubscriptionCheckMiddleware()
    handler = AsyncMock(return_value="handled")
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=802, type="private"),
        from_user=User(id=802, is_bot=False, first_name="Bob"),
    )
    monkeypatch.setattr(subscription_check, "check_subscription_active", AsyncMock(return_value=False))
    data = {
        "handler": SimpleNamespace(flags={"subscription_required": True}),
        "event_from_user": SimpleNamespace(id=802),
        "session_pool": session_pool,
    }

    result = await middleware(handler, message, data)

    assert result is None
    handler.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.integration
async def test_middleware_missing_context_passthrough():
    middleware = SubscriptionCheckMiddleware()
    handler = AsyncMock(return_value="handled")
    data = {"handler": SimpleNamespace(flags={"subscription_required": True})}

    assert await middleware(handler, object(), data) == "handled"


@pytest.mark.integration
async def test_middleware_active_subscription_with_real_check(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=803)
        await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=1),
            True,
        )

    middleware = SubscriptionCheckMiddleware()
    handler = AsyncMock(return_value="handled")
    data = {
        "handler": SimpleNamespace(flags={"subscription_required": True}),
        "event_from_user": SimpleNamespace(id=803),
        "session_pool": session_pool,
    }

    assert await middleware(handler, object(), data) == "handled"
