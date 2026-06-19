import logging
from types import SimpleNamespace

import pytest

from bot.middlewares.update_timing import SlowUpdateLoggingMiddleware


@pytest.mark.unit
async def test_slow_update_middleware_logs_callback_duration(caplog):
    middleware = SlowUpdateLoggingMiddleware(threshold_seconds=0)
    callback = SimpleNamespace(data="connect_device")

    async def handler(event, data):
        return "done"

    with caplog.at_level(logging.WARNING):
        result = await middleware(handler, callback, {"event_from_user": SimpleNamespace(id=42)})

    assert result == "done"
    assert "Slow Telegram update" in caplog.text
    assert "callback=connect_device" in caplog.text
