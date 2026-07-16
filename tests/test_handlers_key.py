from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from datetime import datetime, timedelta, timezone

from bot.handlers import connect_device
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
    monkeypatch.setattr(connect_device, "rotate_user_key", AsyncMock(return_value=(None, "client-config")))
    async def generate_qr_png_bytes(url: str) -> bytes:
        assert callback.answer.await_count == 1
        return b"png"

    monkeypatch.setattr(connect_device, "generate_qr_png_bytes", generate_qr_png_bytes)

    await connect_device.connect_device_handler(callback, session_pool)

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

    await connect_device.connect_device_handler(callback, session_pool)

    callback.answer.assert_awaited_once()
    assert "/start" in callback.answer.await_args.args[0]
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.integration
async def test_get_key_handler_sends_subscription_link_for_panel_subscription(session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=902, username="panel")
        await repo.create_subscription(
            user_id=user.id,
            plan="trial",
            tier="trial",
            panel_username="tg_902",
            sub_token="short",
            subscription_url="https://sub.example/api/sub/short",
            traffic_limit_bytes=10 * 1024**3,
            device_limit=1,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_active=True,
        )

    message = SimpleNamespace(
        answer_document=AsyncMock(),
        answer_photo=AsyncMock(),
        edit_text=AsyncMock(),
        photo=None,
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=902),
        message=message,
        answer=AsyncMock(),
    )
    rotate_user_key = AsyncMock()
    monkeypatch.setattr(connect_device, "rotate_user_key", rotate_user_key)

    await connect_device.connect_device_handler(callback, session_pool)

    rotate_user_key.assert_not_awaited()
    message.answer_document.assert_not_awaited()
    # text-only screen now: the link goes into the edited message, no QR photo
    message.answer_photo.assert_not_awaited()
    message.edit_text.assert_awaited_once()
    assert "https://sub.example/api/sub/short" in message.edit_text.await_args.args[0]


@pytest.mark.integration
async def test_connect_help_handler_shows_manual_instructions(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=903, username="panel")
        await repo.create_subscription(
            user_id=user.id,
            plan="trial",
            tier="trial",
            panel_username="tg_903",
            sub_token="short",
            subscription_url="https://sub.example/api/sub/short",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_active=True,
        )

    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(
        data="connect_help",
        from_user=SimpleNamespace(id=903),
        message=message,
        answer=AsyncMock(),
    )

    await connect_device.connect_help_handler(callback, session_pool)

    callback.answer.assert_awaited_once()
    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Как подключить вручную" in text
    assert "Happ" in text
    assert "https://sub.example/api/sub/short" in text


def test_connect_keyboard_has_happ_help_and_awg_when_configured(monkeypatch):
    monkeypatch.setattr(connect_device, "_awg_available", lambda: True)
    kb_on = connect_device._connect_device_keyboard(happ_url="https://sub.example/happ/x", sub_id=7)
    datas_on = [b.callback_data for row in kb_on.inline_keyboard for b in row]
    urls_on = [b.url for row in kb_on.inline_keyboard for b in row]
    assert "https://sub.example/happ/x" in urls_on
    assert "connect_awg" in datas_on
    assert "connect_help:7" in datas_on
    assert "connect_fix:7" in datas_on  # «Не подключается?»


def test_troubleshoot_text_marks_up_and_down_locations():
    from services.node_probe import LocationHealth

    locs = [
        LocationHealth(flag="🇺🇸", name="США", reachable=True),
        LocationHealth(flag="🇳🇱", name="Нидерланды", reachable=False),
    ]
    text = connect_device._troubleshoot_text(locs)
    assert "Сейчас доступны" in text
    assert "🇺🇸 США ✅" in text
    assert "🇳🇱 Нидерланды ❌" in text
    assert "Hysteria2" in text  # steers mobile users to the DPI-resistant protocol


def test_troubleshoot_text_without_health_data_still_gives_steps():
    text = connect_device._troubleshoot_text([])
    assert "Не подключается" in text
    assert "AmneziaWG" in text
    assert "поддержку" in text


@pytest.mark.integration
async def test_connect_troubleshoot_handler_shows_live_health(session_pool, monkeypatch):
    from services.node_probe import LocationHealth

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=904, username="stuck")
        await repo.create_subscription(
            user_id=user.id, plan="trial", tier="trial", panel_username="tg_904",
            sub_token="tok", subscription_url="https://sub.example/api/sub/tok",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7), is_active=True,
        )

    monkeypatch.setattr(
        connect_device, "_resolve_subscription_url",
        AsyncMock(return_value="https://sub.unlockvpn.site/sub/tok"),
    )
    probe = AsyncMock(return_value=[LocationHealth(flag="🇺🇸", name="США", reachable=True)])
    monkeypatch.setattr(connect_device.node_probe, "probe_subscription", probe)

    message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(
        data="connect_fix",
        from_user=SimpleNamespace(id=904),
        message=message,
        answer=AsyncMock(),
    )

    await connect_device.connect_troubleshoot_handler(callback, session_pool)

    probe.assert_awaited_once_with("https://sub.unlockvpn.site/sub/tok")
    callback.answer.assert_awaited_once()
    text = message.edit_text.await_args.args[0]
    assert "🇺🇸 США ✅" in text

    monkeypatch.setattr(connect_device, "_awg_available", lambda: False)
    datas_off = [b.callback_data for row in connect_device._connect_device_keyboard().inline_keyboard for b in row]
    assert "connect_awg" not in datas_off
    assert "connect_help" in datas_off


@pytest.mark.integration
async def test_connect_awg_handler_sends_configs(session_pool, monkeypatch):
    from services.awg_provision import AwgClientConfig

    async with session_pool() as session:
        await Repository(session).create_user(telegram_id=904, username="awg")

    message = SimpleNamespace(answer=AsyncMock(), answer_document=AsyncMock(), answer_photo=AsyncMock())
    callback = SimpleNamespace(from_user=SimpleNamespace(id=904), message=message, answer=AsyncMock())

    configs = [
        AwgClientConfig(node_code="us", flag="🇺🇸", name="США", config_text="[Interface]\nPrivateKey = a"),
        AwgClientConfig(node_code="nl", flag="🇳🇱", name="Нидерланды", config_text="[Interface]\nPrivateKey = b"),
    ]
    monkeypatch.setattr(connect_device, "ensure_client_configs", AsyncMock(return_value=configs))
    monkeypatch.setattr(connect_device, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))

    await connect_device.connect_awg_handler(callback, session_pool)

    callback.answer.assert_awaited_once()
    assert message.answer_document.await_count == 2
    assert message.answer_photo.await_count == 2


@pytest.mark.integration
async def test_connect_awg_handler_handles_unavailable(session_pool, monkeypatch):
    async with session_pool() as session:
        await Repository(session).create_user(telegram_id=905, username="awg2")

    message = SimpleNamespace(answer=AsyncMock(), answer_document=AsyncMock(), answer_photo=AsyncMock())
    callback = SimpleNamespace(from_user=SimpleNamespace(id=905), message=message, answer=AsyncMock())
    monkeypatch.setattr(connect_device, "ensure_client_configs", AsyncMock(return_value=[]))

    await connect_device.connect_awg_handler(callback, session_pool)

    callback.answer.assert_awaited_once()
    message.answer_document.assert_not_awaited()
