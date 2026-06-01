from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository


@pytest.mark.integration
async def test_user_crud(db_session):
    repo = Repository(db_session)

    user = await repo.create_user(telegram_id=100, username="old")
    duplicate = await repo.create_user(telegram_id=100, username="ignored")
    assert duplicate.id == user.id
    assert duplicate.username == "old"

    existing = await repo.get_or_create_user(telegram_id=100, username="new")
    assert existing.id == user.id
    assert existing.username == "new"

    created = await repo.get_or_create_user(telegram_id=101, username="second")
    assert created.telegram_id == 101
    assert await repo.get_user_by_telegram_id(100) == existing

    users = await repo.list_users()
    assert [item.telegram_id for item in users] == [100, 101]

    updated = await repo.update_user(existing.id, username="updated", is_blocked=True, missing="ignored")
    assert updated.username == "updated"
    assert updated.is_blocked is True

    assert await repo.delete_user(created.id) is True
    assert await repo.delete_user(created.id) is False


@pytest.mark.integration
async def test_subscription_repository_methods(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=200)
    now = datetime.now(timezone.utc)
    old = await repo.create_subscription(user.id, "1m", now - timedelta(days=40), now - timedelta(days=10), True)
    inactive_future = await repo.create_subscription(user.id, "3m", now, now + timedelta(days=10), False)
    latest = await repo.create_subscription(user.id, "6m", now, now + timedelta(days=20), True)

    assert await repo.get_subscription(old.id) == old
    assert await repo.get_latest_subscription(user.id) == latest
    assert await repo.get_active_subscription(user.id) == latest
    assert [sub.id for sub in await repo.list_subscriptions_by_user(user.id)] == [latest.id, inactive_future.id, old.id]

    expiring = await repo.create_subscription(user.id, "1m", now, now + timedelta(days=2), True)
    assert expiring in await repo.get_expiring_subscriptions(days=3)
    await repo.mark_subscription_reminded(expiring.id)
    await db_session.refresh(expiring)
    assert expiring.last_reminded_at is not None
    assert expiring not in await repo.get_expiring_subscriptions(days=3)

    expired_active = await repo.create_subscription(user.id, "1m", now - timedelta(days=31), now - timedelta(days=1), True)
    assert expired_active in await repo.get_expired_active_subscriptions()

    await repo.deactivate_user_subscriptions(user.id)
    await db_session.refresh(latest)
    assert latest.is_active is False
    assert await repo.get_active_subscription(user.id) is None

    assert await repo.delete_subscription(inactive_future.id) is True
    assert await repo.delete_subscription(inactive_future.id) is False


@pytest.mark.integration
async def test_wireguard_key_repository_methods(db_session):
    repo = Repository(db_session)
    user1 = await repo.create_user(telegram_id=300)
    user2 = await repo.create_user(telegram_id=301)
    key1 = await repo.create_wireguard_key(user1.id, "PUB1", "PRIV1", "10.9.0.2", "/one.conf")
    key2 = await repo.create_wireguard_key(user2.id, "PUB2", "PRIV2", "10.9.0.3", "/two.conf")

    assert await repo.get_wireguard_key(key1.id) == key1
    assert await repo.get_wireguard_key_by_user_id(user1.id) == key1
    assert await repo.get_wireguard_key_by_public_key("PUB2") == key2
    assert await repo.get_all_wireguard_keys() == [key1, key2]
    assert await repo.get_used_wireguard_ips() == {"10.9.0.2", "10.9.0.3"}

    updated = await repo.update_wireguard_key(key1.id, public_key="PUB1NEW", ignored="value")
    assert updated.id == key1.id
    assert updated.public_key == "PUB1NEW"
    assert await repo.update_wireguard_key(9999, public_key="missing") is None

    assert await repo.delete_wireguard_key(key2.id) is True
    assert await repo.delete_wireguard_key(key2.id) is False


@pytest.mark.integration
async def test_payment_repository_methods(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=400)
    basic = await repo.create_payment(user.id, amount=100, invoice_payload="payload-basic")
    payment = await repo.create_cryptobot_payment(
        user_id=user.id,
        amount=199,
        external_invoice_id="invoice-1",
        invoice_payload="payload-crypto",
        plan="1m",
    )
    basic_id = basic.id
    user_id = user.id
    payment_id = payment.id

    assert await repo.get_payment(basic.id) == basic
    assert await repo.get_payment_by_payload("payload-basic") == basic
    assert await repo.get_payment_by_external_id("invoice-1") == payment
    assert [item.id for item in await repo.list_payments_by_user(user.id)] == [payment.id, basic.id]

    completed = await repo.complete_payment_by_external_id("invoice-1")
    assert completed.id == payment.id
    assert completed.status == "completed"
    assert completed.provider_payment_charge_id == "invoice-1"
    assert await repo.complete_payment_by_external_id("invoice-1") is None

    updated = await repo.update_payment_status(basic_id, "failed")
    assert updated.status == "failed"
    assert await repo.update_payment_status(9999, "failed") is None

    completed_by_payload = await repo.complete_payment_by_payload("payload-basic", "tg", "provider")
    assert completed_by_payload.status == "completed"
    assert completed_by_payload.telegram_payment_charge_id == "tg"
    assert completed_by_payload.provider_payment_charge_id == "provider"
    assert await repo.complete_payment_by_payload("missing", "tg") is None
