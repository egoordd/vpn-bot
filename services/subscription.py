from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Subscription
from database.repository import Repository
from services.payment import PLANS


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def activate_subscription(session: AsyncSession, user_id: int, plan: str) -> Subscription:
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")

    repo = Repository(session)
    now = datetime.now(timezone.utc)
    latest = await repo.get_latest_subscription(user_id)
    starts_at = now
    if latest and latest.is_active and _aware(latest.expires_at) > now:
        starts_at = _aware(latest.expires_at)

    await repo.deactivate_user_subscriptions(user_id)
    expires_at = starts_at + timedelta(days=int(PLANS[plan]["days"]))
    return await repo.create_subscription(
        user_id=user_id,
        plan=plan,
        started_at=starts_at,
        expires_at=expires_at,
        is_active=True,
    )


async def check_subscription_active(session: AsyncSession, user_id: int) -> bool:
    repo = Repository(session)
    subscription = await repo.get_active_subscription(user_id)
    return subscription is not None


async def get_subscription_info(session: AsyncSession, user_id: int) -> dict[str, object]:
    repo = Repository(session)
    subscription = await repo.get_latest_subscription(user_id)
    if subscription is None:
        return {
            "exists": False,
            "is_active": False,
            "plan": None,
            "plan_title": None,
            "started_at": None,
            "expires_at": None,
        }

    now = datetime.now(timezone.utc)
    active = subscription.is_active and _aware(subscription.expires_at) > now
    plan_data = PLANS.get(subscription.plan, {})
    return {
        "exists": True,
        "is_active": active,
        "plan": subscription.plan,
        "plan_title": plan_data.get("title", subscription.plan),
        "started_at": subscription.started_at,
        "expires_at": subscription.expires_at,
    }
