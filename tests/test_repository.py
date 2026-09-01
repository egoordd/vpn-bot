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
async def test_panel_subscription_repository_methods(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=250)
    now = datetime.now(timezone.utc)
    panel_subscription = await repo.create_subscription(
        user_id=user.id,
        plan="trial",
        tier="trial",
        panel_username="tg_250",
        sub_token="old",
        subscription_url="https://sub.example/old",
        started_at=now,
        expires_at=now + timedelta(days=7),
        is_active=True,
    )
    await repo.create_subscription(
        user_id=user.id,
        plan="legacy",
        started_at=now,
        expires_at=now + timedelta(days=7),
        is_active=True,
    )

    assert await repo.list_active_panel_subscriptions() == [panel_subscription]

    updated = await repo.update_subscription(
        panel_subscription.id,
        traffic_used_bytes=123,
        status="active",
        ignored="value",
    )
    assert updated.traffic_used_bytes == 123
    assert updated.status == "active"
    assert await repo.update_subscription(9999, status="missing") is None


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
    payment = await repo.create_yookassa_payment(
        user_id=user.id,
        amount=14900,
        external_invoice_id="invoice-1",
        invoice_payload="payload-card",
        plan="standard_1m",
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


@pytest.mark.integration
async def test_plan_repository_methods(db_session):
    repo = Repository(db_session)

    plan = await repo.upsert_plan(
        code="standard_1m",
        title="Standard 1 month",
        tier="standard",
        duration_days=30,
        price_rub=149,
        crypto_amount="1.99",
        traffic_limit_bytes=150 * 1024**3,
        device_limit=3,
        sort_order=10,
    )
    assert await repo.get_plan("standard_1m") == plan

    updated = await repo.upsert_plan(
        code="standard_1m",
        title="Standard updated",
        tier="standard",
        duration_days=31,
        price_rub=199,
        crypto_amount="2.49",
        traffic_limit_bytes=None,
        device_limit=5,
        is_active=False,
        sort_order=20,
    )
    assert updated.code == plan.code
    assert updated.title == "Standard updated"
    assert await repo.list_plans(active_only=True) == []
    assert [item.code for item in await repo.list_plans(active_only=False)] == ["standard_1m"]


@pytest.mark.integration
async def test_node_repository_methods(db_session):
    repo = Repository(db_session)

    premium_empty = await repo.create_node(
        tier="premium",
        capacity=10,
        region="de-fra",
        provider="vultr",
        ip_address="203.0.113.10",
        provider_instance_id="vultr-instance-1",
        panel_node_id="panel-node-1",
        current_users=2,
        static_ips=["198.51.100.10"],
        name="fra-premium-1",
    )
    premium_busy = await repo.create_node(
        tier="premium",
        capacity=10,
        region="de-fra",
        provider="vultr",
        ip_address="203.0.113.11",
        panel_node_id="panel-node-2",
        current_users=10,
    )
    premium_other_region = await repo.create_node(
        tier="premium",
        capacity=5,
        region="nl-ams",
        provider="vultr",
        ip_address="203.0.113.12",
        panel_node_id="panel-node-3",
        current_users=0,
    )
    await repo.create_node(
        tier="standard",
        capacity=100,
        region="de-fra",
        provider="vultr",
        ip_address="203.0.113.13",
        panel_node_id="panel-node-4",
        current_users=0,
    )
    premium_draining = await repo.create_node(
        tier="premium",
        capacity=10,
        region="de-fra",
        provider="vultr",
        ip_address="203.0.113.14",
        panel_node_id="panel-node-5",
        current_users=0,
        status="draining",
    )

    assert await repo.get_node(premium_empty.id) == premium_empty
    assert await repo.get_node_by_panel_node_id("panel-node-1") == premium_empty
    assert await repo.get_node_by_provider_instance_id("vultr-instance-1") == premium_empty
    assert premium_empty.static_ips == ["198.51.100.10"]
    assert [node.id for node in await repo.list_nodes(tier="premium", region="de-fra")] == [
        premium_empty.id,
        premium_busy.id,
        premium_draining.id,
    ]
    assert [node.id for node in await repo.list_available_nodes("premium")] == [
        premium_other_region.id,
        premium_empty.id,
    ]
    assert [node.id for node in await repo.list_available_nodes("premium", region="de-fra")] == [premium_empty.id]

    updated = await repo.update_node(
        premium_empty.id,
        current_users=3,
        status="active",
        static_ips=["198.51.100.10", "198.51.100.11"],
        ignored="value",
    )
    assert updated.current_users == 3
    assert updated.static_ips == ["198.51.100.10", "198.51.100.11"]
    assert await repo.update_node(9999, status="missing") is None

    assert await repo.delete_node(premium_busy.id) is True
    assert await repo.delete_node(premium_busy.id) is False


@pytest.mark.integration
async def test_traffic_limited_subscriptions_skip_rows_a_renewal_superseded(db_session):
    """Only the newest row per panel account may be revived.

    A renewal deactivates the earlier rows in the lane but leaves their status
    alone, so an old `limited` row can outlive its replacement. Reviving one
    would leave the user holding two live subscriptions against a single panel
    account.
    """
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=7101)
    now = datetime.now(timezone.utc)

    superseded = await repo.create_subscription(
        user_id=user.id,
        plan="standard_1m",
        tier="standard",
        panel_username="tg_7101",
        traffic_limit_bytes=150 * 1024**3,
        started_at=now - timedelta(days=20),
        expires_at=now + timedelta(days=10),
        is_active=False,
        status="limited",
    )
    newest = await repo.create_subscription(
        user_id=user.id,
        plan="standard_1m",
        tier="standard",
        panel_username="tg_7101",
        traffic_limit_bytes=150 * 1024**3,
        started_at=now,
        expires_at=now + timedelta(days=40),
        is_active=False,
        status="limited",
    )

    parked = await repo.list_traffic_limited_subscriptions()

    assert [item.id for item in parked] == [newest.id]
    assert superseded.id not in {item.id for item in parked}


@pytest.mark.integration
async def test_traffic_limited_subscriptions_ignore_expired_and_healthy_rows(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=7102)
    now = datetime.now(timezone.utc)

    await repo.create_subscription(
        user_id=user.id,
        plan="standard_1m",
        tier="standard",
        panel_username="tg_7102_expired",
        started_at=now - timedelta(days=60),
        expires_at=now - timedelta(days=1),
        is_active=False,
        status="limited",
    )
    await repo.create_subscription(
        user_id=user.id,
        plan="standard_1m",
        tier="standard",
        panel_username="tg_7102_active",
        started_at=now,
        expires_at=now + timedelta(days=30),
        is_active=True,
        status="active",
    )

    assert await repo.list_traffic_limited_subscriptions() == []
