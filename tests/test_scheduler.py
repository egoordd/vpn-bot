from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from scheduler import tasks
from services.payment import create_invoice_payload
from services.wireguard import WireGuardError


@pytest.mark.integration
async def test_poll_cryptobot_payments_crypto_error_returns(fake_bot, session_pool, monkeypatch):
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(side_effect=RuntimeError("down")))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    fake_bot.send_message.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_invoice_without_id(fake_bot, session_pool, monkeypatch):
    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"payload": "x"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_no_matching_payment(fake_bot, session_pool, monkeypatch):
    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"invoice_id": "missing"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_non_pending_payment(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=500)
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-done", "payload", "1m")
        await repo.update_payment_status(payment.id, "completed")

    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"invoice_id": "inv-done"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_invalid_payload(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=501)
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-bad", "bad-payload", "1m")

    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"invoice_id": "inv-bad"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)
        assert refreshed.status == "pending"
    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_payload_user_mismatch(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=502)
        other = await repo.create_user(telegram_id=503)
        payload = create_invoice_payload(other.id, "1m")
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-mismatch", payload, "1m")

    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-mismatch", "payload": payload}]),
    )
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)
        assert refreshed.status == "pending"
    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_happy_path(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=504)
        payload = create_invoice_payload(user.id, "1m")
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-paid", payload, "1m")

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-paid", "payload": payload}]),
    )
    ensure_user_peer = AsyncMock(return_value=(None, "client-config"))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)
    monkeypatch.setattr(tasks, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        repo = Repository(session)
        refreshed = await repo.get_payment(payment.id)
        subscription = await repo.get_active_subscription(user.id)

    assert refreshed.status == "completed"
    assert subscription is not None
    ensure_user_peer.assert_awaited_once()
    fake_bot.send_message.assert_awaited_once()
    fake_bot.send_document.assert_awaited_once()
    fake_bot.send_photo.assert_awaited_once()


@pytest.mark.integration
async def test_check_expiring_subscriptions_sends_and_marks(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=600)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=2),
            True,
        )

    await tasks.check_expiring_subscriptions(fake_bot, session_pool)

    fake_bot.send_message.assert_awaited_once()
    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.last_reminded_at is not None


@pytest.mark.integration
async def test_check_expiring_subscriptions_catches_send_errors(session_pool):
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=601)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=2),
            True,
        )

    await tasks.check_expiring_subscriptions(bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.last_reminded_at is None


@pytest.mark.integration
async def test_deactivate_expired_subscriptions_removes_peer_and_notifies(fake_bot, session_pool, monkeypatch):
    remove_peer = AsyncMock()
    monkeypatch.setattr(tasks, "remove_peer", remove_peer)
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=700)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc) - timedelta(days=31),
            datetime.now(timezone.utc) - timedelta(days=1),
            True,
        )
        await repo.create_wireguard_key(user.id, "PUB", "PRIV", "10.9.0.2", "/client.conf")

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    remove_peer.assert_awaited_once_with("PUB")
    fake_bot.send_message.assert_awaited_once()
    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.is_active is False


@pytest.mark.integration
async def test_deactivate_expired_subscriptions_catches_remove_peer_errors(fake_bot, session_pool, monkeypatch):
    remove_peer = AsyncMock(side_effect=WireGuardError("cannot remove"))
    monkeypatch.setattr(tasks, "remove_peer", remove_peer)
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=701)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc) - timedelta(days=31),
            datetime.now(timezone.utc) - timedelta(days=1),
            True,
        )
        await repo.create_wireguard_key(user.id, "PUBERR", "PRIV", "10.9.0.2", "/client.conf")

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    remove_peer.assert_awaited_once_with("PUBERR")
    fake_bot.send_message.assert_awaited_once()
    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.is_active is False


@pytest.mark.unit
def test_access_text_and_aware_helpers():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = tasks._aware(naive)

    assert aware.tzinfo == timezone.utc
    assert "01.01.2026 12:00 UTC" in tasks._access_text(naive)
