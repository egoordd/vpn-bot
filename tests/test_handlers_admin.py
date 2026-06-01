from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import admin


@pytest.mark.integration
async def test_admin_only_guard_rejects_non_admin(session_pool, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "1")
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=2, username="not_admin"),
        answer=AsyncMock(),
        answer_document=AsyncMock(),
        answer_photo=AsyncMock(),
    )

    await admin.test_key_handler(message, session_pool)

    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0]
    message.answer_document.assert_not_awaited()
    message.answer_photo.assert_not_awaited()


@pytest.mark.integration
async def test_admin_test_key_handler_sends_key_for_admin(session_pool, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "3")
    monkeypatch.setattr(admin, "activate_subscription", AsyncMock())
    monkeypatch.setattr(admin, "ensure_user_peer", AsyncMock(return_value=(None, "client-config")))
    monkeypatch.setattr(admin, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=3, username="admin"),
        answer=AsyncMock(),
        answer_document=AsyncMock(),
        answer_photo=AsyncMock(),
    )

    await admin.test_key_handler(message, session_pool)

    message.answer.assert_not_awaited()
    message.answer_document.assert_awaited_once()
    message.answer_photo.assert_awaited_once()
