from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class SlowUpdateLoggingMiddleware(BaseMiddleware):
    """Log handlers that exceed the response-time budget without logging text."""

    def __init__(self, threshold_seconds: float = 1.0):
        self.threshold_seconds = threshold_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        started_at = perf_counter()
        try:
            return await handler(event, data)
        finally:
            elapsed = perf_counter() - started_at
            if elapsed >= self.threshold_seconds:
                user = data.get("event_from_user")
                callback_data = getattr(event, "data", None)
                logger.warning(
                    "Slow Telegram update: type=%s user_id=%s callback=%s duration=%.3fs",
                    type(event).__name__,
                    getattr(user, "id", None),
                    callback_data,
                    elapsed,
                )
