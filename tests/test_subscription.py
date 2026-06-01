from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services.payment import PLANS
from services.subscription import _aware, activate_subscription, check_subscription_active, get_subscription_info


@pytest.mark.integration
async def test_activate_subscription_unknown_plan_raises(db_session):
    with pytest.raises(ValueError):
        await activate_subscription(db_session, user_id=1, plan="unknown")


@pytest.mark.integration
async def test_activate_subscription_without_prior_subscription_starts_now(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=1, username="alice")

    before = datetime.now(timezone.utc)
    subscription = await activate_subscription(db_session, user.id, "1m")
    after = datetime.now(timezone.utc)

    assert _aware(subscription.started_at) >= before - timedelta(seconds=1)
    assert _aware(subscription.started_at) <= after + timedelta(seconds=1)
    assert _aware(subscription.expires_at) == _aware(subscription.started_at) + timedelta(days=PLANS["1m"]["days"])
    assert subscription.is_active is True


@pytest.mark.integration
async def test_activate_subscription_stacks_existing_active_subscription(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=2)
    now = datetime.now(timezone.utc)
    old = await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=10),
        is_active=True,
    )

    new_subscription = await activate_subscription(db_session, user.id, "3m")
    await db_session.refresh(old)

    assert _aware(new_subscription.started_at) == _aware(old.expires_at)
    assert _aware(new_subscription.expires_at) == _aware(old.expires_at) + timedelta(days=PLANS["3m"]["days"])
    assert old.is_active is False
    assert new_subscription.is_active is True


@pytest.mark.integration
async def test_check_subscription_active(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=3)

    assert await check_subscription_active(db_session, user.id) is False

    expired = datetime.now(timezone.utc) - timedelta(days=1)
    await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=expired - timedelta(days=30),
        expires_at=expired,
        is_active=True,
    )
    assert await check_subscription_active(db_session, user.id) is False

    await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )
    assert await check_subscription_active(db_session, user.id) is True


@pytest.mark.integration
async def test_get_subscription_info_states(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=4)

    assert await get_subscription_info(db_session, user.id) == {
        "exists": False,
        "is_active": False,
        "plan": None,
        "plan_title": None,
        "started_at": None,
        "expires_at": None,
    }

    active = await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )
    info = await get_subscription_info(db_session, user.id)
    assert info["exists"] is True
    assert info["is_active"] is True
    assert info["plan_title"] == PLANS["1m"]["title"]
    assert info["expires_at"] == active.expires_at

    expired_user = await repo.create_user(telegram_id=5)
    expired = await repo.create_subscription(
        user_id=expired_user.id,
        plan="3m",
        started_at=datetime.now(timezone.utc) - timedelta(days=91),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        is_active=True,
    )
    info = await get_subscription_info(db_session, expired_user.id)
    assert info["exists"] is True
    assert info["is_active"] is False
    assert info["plan_title"] == PLANS["3m"]["title"]
    assert info["expires_at"] == expired.expires_at


@pytest.mark.unit
def test_aware_converts_naive_and_preserves_aware():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    assert _aware(naive).tzinfo == timezone.utc
    assert _aware(aware) is aware
