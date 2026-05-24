from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.repository import Repository
from services.subscription import check_subscription_active


class SubscriptionCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        handler_object = data.get("handler")
        flags = getattr(handler_object, "flags", {}) if handler_object else {}
        if not flags.get("subscription_required"):
            return await handler(event, data)

        telegram_user = data.get("event_from_user")
        session_pool: async_sessionmaker[AsyncSession] | None = data.get("session_pool")
        if telegram_user is None or session_pool is None:
            return await handler(event, data)

        async with session_pool() as session:
            repo = Repository(session)
            db_user = await repo.get_user_by_telegram_id(telegram_user.id)
            if db_user and await check_subscription_active(session, db_user.id):
                return await handler(event, data)

        text = "Для этого действия нужна активная подписка. Оформите VPN в разделе «Купить VPN»."
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
            return None
        if isinstance(event, Message):
            await event.answer(text)
            return None
        return None
