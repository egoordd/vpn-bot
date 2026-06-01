from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import key
from database.repository import Repository


@pytest.mark.integration
async def test_get_key_handler_sends_document_and_photo(session_pool, monkeypatch):
    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=900, username="alice")

    message = SimpleNamespace(answer_document=AsyncMock(), answer_photo=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=900),
        message=message,
        answer=AsyncMock(),
    )
    monkeypatch.setattr(key, "rotate_user_key", AsyncMock(return_value=(None, "client-config")))
    monkeypatch.setattr(key, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))

    await key.get_key_handler(callback, session_pool)

    assert user.id
    message.answer_document.assert_awaited_once()
    message.answer_photo.assert_awaited_once()
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_get_key_handler_missing_user_alerts(session_pool):
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=901),
        message=SimpleNamespace(answer_document=AsyncMock(), answer_photo=AsyncMock()),
        answer=AsyncMock(),
    )

    await key.get_key_handler(callback, session_pool)

    callback.answer.assert_awaited_once()
    assert "/start" in callback.answer.await_args.args[0]
    assert callback.answer.await_args.kwargs["show_alert"] is True
