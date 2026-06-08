from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import admin
from database.repository import Repository
from services.panel_gateway import PanelAccount


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
    activate_subscription = AsyncMock()
    monkeypatch.setattr(admin, "activate_subscription", activate_subscription)
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
    assert activate_subscription.await_args.kwargs["plan"] == "standard_1m"
    message.answer_document.assert_awaited_once()
    message.answer_photo.assert_awaited_once()


@pytest.mark.integration
async def test_sync_traffic_handler_runs_manual_sync_for_admin(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    traffic_sync = AsyncMock(return_value=3)
    monkeypatch.setattr(admin, "traffic_sync", traffic_sync)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=4, username="admin"),
        answer=AsyncMock(),
    )

    await admin.sync_traffic_handler(message, session_pool, fake_bot)

    traffic_sync.assert_awaited_once_with(bot=fake_bot, session_pool=session_pool)
    message.answer.assert_awaited_once()
    assert "3" in message.answer.await_args.args[0]


@pytest.mark.integration
async def test_sync_traffic_handler_rejects_non_admin(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    traffic_sync = AsyncMock()
    monkeypatch.setattr(admin, "traffic_sync", traffic_sync)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=5, username="not_admin"),
        answer=AsyncMock(),
    )

    await admin.sync_traffic_handler(message, session_pool, fake_bot)

    traffic_sync.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert "администраторам" in message.answer.await_args.args[0]


class FakePanelGateway:
    async def get_user(self, username: str) -> PanelAccount:
        return PanelAccount(
            username=username,
            short_uuid="short",
            subscription_url="https://sub.example/api/sub/short",
            status="ACTIVE",
            expire_at="2026-07-03T00:00:00Z",
            traffic_limit_bytes=10 * 1024**3,
            used_traffic_bytes=2 * 1024**3,
            lifetime_used_traffic_bytes=2 * 1024**3,
            device_limit=3,
            provider="test",
        )


@pytest.mark.integration
async def test_panel_user_handler_shows_panel_user(session_pool, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "6")
    monkeypatch.setattr(admin, "get_panel_gateway", lambda: FakePanelGateway())
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=606)
        await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="tg_606",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            is_active=False,
        )

    message = SimpleNamespace(
        text="/panel_user 606",
        from_user=SimpleNamespace(id=6, username="admin"),
        answer=AsyncMock(),
    )

    await admin.panel_user_handler(message, session_pool)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "tg_606" in text
    assert "ACTIVE" in text
    assert "2.0 ГБ / 10.0 ГБ" in text


@pytest.mark.integration
async def test_panel_user_handler_rejects_invalid_arg(session_pool, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "6")
    message = SimpleNamespace(
        text="/panel_user nope",
        from_user=SimpleNamespace(id=6, username="admin"),
        answer=AsyncMock(),
    )

    await admin.panel_user_handler(message, session_pool)

    message.answer.assert_awaited_once()
    assert "Использование" in message.answer.await_args.args[0]
