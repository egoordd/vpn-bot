from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings  # kept as a compatibility hook for tests and live monkeypatches
from database.models import Subscription
from database.repository import Repository
from services.panel_gateway import (
    PanelGateway,
    PanelUserNotFoundError,
    RemnawavePanelGateway,
    get_panel_gateway,
)
from services.payment import PLANS
from services.tariffs import TARIFFS, Tariff, resolve_tariff


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def activate_subscription(session: AsyncSession, user_id: int, plan: str) -> Subscription:
    plan_data = PLANS.get(plan)
    if plan_data is None:
        try:
            tariff = resolve_tariff(plan)
        except ValueError as exc:
            raise ValueError(f"Unknown plan: {plan}") from exc
        plan_code = tariff.code
        days = tariff.duration_days
        tier = tariff.tier
        traffic_limit_bytes = tariff.traffic_limit_bytes
        device_limit = tariff.device_limit
    else:
        plan_code = plan
        days = int(plan_data["days"])
        tier = "standard"
        traffic_limit_bytes = None
        device_limit = None

    repo = Repository(session)
    now = datetime.now(timezone.utc)
    latest = await repo.get_latest_subscription(user_id)
    starts_at = now
    if latest and latest.is_active and _aware(latest.expires_at) > now:
        starts_at = _aware(latest.expires_at)

    await repo.deactivate_user_subscriptions(user_id)
    expires_at = starts_at + timedelta(days=days)
    return await repo.create_subscription(
        user_id=user_id,
        plan=plan_code,
        tier=tier,
        traffic_limit_bytes=traffic_limit_bytes,
        device_limit=device_limit,
        started_at=starts_at,
        expires_at=expires_at,
        is_active=True,
    )


async def sync_default_plans(session: AsyncSession) -> None:
    repo = Repository(session)
    for tariff in TARIFFS.values():
        await repo.upsert_plan(
            code=tariff.code,
            title=tariff.title,
            tier=tariff.tier,
            duration_days=tariff.duration_days,
            price_rub=tariff.price_rub,
            crypto_amount=tariff.crypto_amount,
            traffic_limit_bytes=tariff.traffic_limit_bytes,
            device_limit=tariff.device_limit,
            description=tariff.description,
            sort_order=tariff.sort_order,
        )


async def _panel_user_exists(panel_gateway: PanelGateway, panel_username: str) -> bool:
    try:
        await panel_gateway.get_user(panel_username)
    except PanelUserNotFoundError:
        return False
    return True


async def activate_panel_subscription(
    session: AsyncSession,
    user_id: int,
    plan: str,
    panel_client: Any | None = None,
    panel_gateway: PanelGateway | None = None,
    region: str | None = None,
) -> Subscription:
    tariff: Tariff = resolve_tariff(plan)
    region_inbounds = settings.marzban_inbounds_for_region(region)
    repo = Repository(session)
    user = await repo.get_user(user_id)
    if user is None:
        raise ValueError(f"Unknown user_id: {user_id}")

    now = datetime.now(timezone.utc)
    latest = await repo.get_latest_subscription(user_id)
    starts_at = now
    if latest and latest.is_active and _aware(latest.expires_at) > now:
        starts_at = _aware(latest.expires_at)

    expires_at = starts_at + timedelta(days=tariff.duration_days)
    if panel_gateway is not None and panel_client is not None:
        raise ValueError("panel_gateway and panel_client are mutually exclusive")
    gateway = panel_gateway or (RemnawavePanelGateway(panel_client) if panel_client is not None else get_panel_gateway())
    panel_username = latest.panel_username if latest and latest.panel_username else gateway.build_username(user.telegram_id)

    if await _panel_user_exists(gateway, panel_username):
        panel_user = await gateway.modify_user(
            username=panel_username,
            expire_at=expires_at,
            traffic_limit_bytes=tariff.traffic_limit_bytes,
            device_limit=tariff.device_limit,
            status="active",
            tag=tariff.tier,
            inbounds=region_inbounds,
        )
    else:
        panel_user = await gateway.create_user(
            username=panel_username,
            expire_at=expires_at,
            traffic_limit_bytes=tariff.traffic_limit_bytes,
            device_limit=tariff.device_limit,
            telegram_id=user.telegram_id,
            status="active",
            description=f"Telegram user {user.telegram_id}",
            tag=tariff.tier,
            inbounds=region_inbounds,
        )

    await repo.deactivate_user_subscriptions(user_id)
    return await repo.create_subscription(
        user_id=user_id,
        plan=tariff.code,
        tier=tariff.tier,
        panel_username=panel_user.username,
        sub_token=panel_user.short_uuid,
        subscription_url=panel_user.subscription_url,
        traffic_limit_bytes=tariff.traffic_limit_bytes,
        traffic_used_bytes=panel_user.used_traffic_bytes,
        device_limit=tariff.device_limit,
        status=panel_user.status.lower(),
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
    if plan_data:
        plan_title = plan_data.get("title", subscription.plan)
    else:
        try:
            plan_title = resolve_tariff(subscription.plan).title
        except ValueError:
            plan_title = subscription.plan

    return {
        "exists": True,
        "is_active": active,
        "plan": subscription.plan,
        "plan_title": plan_title,
        "tier": subscription.tier,
        "panel_username": subscription.panel_username,
        "sub_token": subscription.sub_token,
        "subscription_url": subscription.subscription_url,
        "traffic_limit_bytes": subscription.traffic_limit_bytes,
        "traffic_used_bytes": subscription.traffic_used_bytes,
        "device_limit": subscription.device_limit,
        "status": subscription.status,
        "started_at": subscription.started_at,
        "expires_at": subscription.expires_at,
    }
