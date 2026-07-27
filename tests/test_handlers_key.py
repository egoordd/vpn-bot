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


def test_connect_keyboard_has_site_auto_and_help_only():
    kb = connect_device._connect_device_keyboard(
        sub_id=7,
        site_url="https://site/connect",
        auto_url="https://sub.example/happ/x/auto",
    )
    urls = [b.url for row in kb.inline_keyboard for b in row if b.url]
    datas = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    # only site link + «Авто-обход» (all locations) + manual help — no manual Happ, no AWG
    assert "https://site/connect" in urls
    assert "https://sub.example/happ/x/auto" in urls
    assert "connect_help:7" in datas
    assert "connect_awg" not in datas
    assert not any("выбор вручную" in t for t in labels)
    assert any("Авто-обход" in t for t in labels)


def test_connect_keyboard_omits_urls_when_absent():
    datas = [
        b.callback_data
        for row in connect_device._connect_device_keyboard().inline_keyboard
        for b in row
        if b.callback_data
    ]
    urls = [b.url for row in connect_device._connect_device_keyboard().inline_keyboard for b in row if b.url]
    assert "connect_help" in datas
    assert urls == []
