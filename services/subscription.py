import logging
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

logger = logging.getLogger(__name__)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def to_gateway_subscription_url(marzban_url: str | None) -> str | None:
    """Rewrite a raw Marzban subscription URL to the multi-protocol gateway.

    The gateway serves the same per-user token but augments the VLESS-only
    Marzban output with a Hysteria2 entry per location. When SUB_GATEWAY_URL
    is unset, or the URL isn't a recognizable /sub/<token> link, the original
    URL is returned unchanged so clients still get a working VLESS subscription.
    """
    base = settings.SUB_GATEWAY_URL.strip().rstrip("/")
    if not base or not marzban_url or "/sub/" not in marzban_url:
        return marzban_url
    token = marzban_url.rsplit("/sub/", 1)[-1].strip("/")
    if not token:
        return marzban_url
    return f"{base}/sub/{token}"


def connect_page_url(sub_url: str | None) -> str | None:
    """Build the site's /connect landing link for a subscription.

    The sub link travels in the URL *fragment* (`#sub=...`) so it never reaches
    the server or referrers — the page reads it client-side to offer one-tap app
    import + setup instructions. Returns None when WEB_BASE_URL is unset.
    """
    import urllib.parse

    base = settings.WEB_BASE_URL.strip().rstrip("/")
    if not base or not sub_url:
        return None
    return f"{base}/connect#sub={urllib.parse.quote(sub_url, safe='')}"


def to_happ_import_url(gateway_url: str | None, auto: bool = False) -> str | None:
    """Map a gateway `/sub/<token>` URL to the `/happ/<token>` redirect.

    The redirect endpoint bounces the browser into the `happ://add/...` deep
    link so a single HTTPS button (Telegram rejects custom schemes) opens Happ
    and imports the subscription. Returns None when the URL isn't a recognizable
    `/sub/<token>` gateway link.

    ``auto=True`` targets the «⚡️ Авто-обход» subscription flavor
    (`/sub/<token>/auto`): the gateway serves it with Happ app-management
    headers that make the app auto-connect to the lowest-latency server.
    """
    if not gateway_url or "/sub/" not in gateway_url:
        return None
    happ_url = gateway_url.replace("/sub/", "/happ/", 1)
    return f"{happ_url.rstrip('/')}/auto" if auto else happ_url


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
    # Two independent billing lanes: premium (location-specific) and non-premium
    # (trial + standard, main server). Each lane has its own panel user, expiry
    # and link — buying in one lane never overwrites the other.
    is_premium = tariff.tier == "premium"
    latest = await repo.get_latest_subscription_in_lane(user_id, is_premium)
    starts_at = now
    if latest and latest.is_active and _aware(latest.expires_at) > now:
        starts_at = _aware(latest.expires_at)

    expires_at = starts_at + timedelta(days=tariff.duration_days)
    if panel_gateway is not None and panel_client is not None:
        raise ValueError("panel_gateway and panel_client are mutually exclusive")
    gateway = panel_gateway or (RemnawavePanelGateway(panel_client) if panel_client is not None else get_panel_gateway())
    if latest and latest.panel_username:
        panel_username = latest.panel_username
    else:
        base_username = gateway.build_username(user.telegram_id)
        # Non-premium lane keeps the bare username (backward compatible); premium
        # gets a distinct panel user so the two lanes don't overwrite each other.
        panel_username = f"{base_username}p" if is_premium else base_username

    if await _panel_user_exists(gateway, panel_username):
        panel_user = await gateway.modify_user(
            username=panel_username,
            expire_at=expires_at,
            traffic_limit_bytes=tariff.traffic_limit_bytes,
            device_limit=tariff.device_limit,
            status="active",
            tag=tariff.tier,
            inbounds=region_inbounds,
            traffic_resets_monthly=tariff.traffic_resets_monthly,
        )
        # A renewal reuses the panel account, and the panel counts traffic
        # against the account, not against the period that was paid for. Left
        # alone, last month's consumption is still sitting there when the new
        # month starts, so someone who used 140 of 150 GB and then paid again
        # would get 10 GB for their money. Zero it at the boundary; this also
        # re-anchors the panel's own 30-day refill to the day they paid.
        if tariff.traffic_resets_monthly:
            try:
                panel_user = await gateway.reset_traffic(panel_username)
            except Exception:
                # Deliberately broad: the customer has paid, and nothing about
                # zeroing a counter is worth losing that. A panel that cannot
                # reset leaves them on the carried-over counter until the
                # rolling sweep clears it — bad, but recoverable. A crash here
                # would drop the purchase itself, which is not.
                logger.exception("Failed to reset traffic on renewal for %s", panel_username)
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
            traffic_resets_monthly=tariff.traffic_resets_monthly,
        )

    await repo.deactivate_subscriptions_in_lane(user_id, is_premium)
    subscription = await repo.create_subscription(
        user_id=user_id,
        plan=tariff.code,
        tier=tariff.tier,
        region=region if is_premium else None,
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
    if tariff.tier == "trial":
        await repo.record_funnel_event(user_id, "trial")
    return subscription


class StaticRegionError(RuntimeError):
    """Raised when a premium region has no static panel node configured."""


async def switch_premium_region(
    session: AsyncSession,
    user_id: int,
    region: str,
    panel_gateway: PanelGateway | None = None,
) -> Subscription:
    """Move an active premium subscription to another static region.

    Re-points the premium panel user to the region's inbound (no extra charge,
    same expiry) — works for static nodes without the autoscaler.
    """
    region_inbounds = settings.marzban_inbounds_for_region(region)
    if region_inbounds is None:
        raise StaticRegionError(f"No static node for region: {region}")

    repo = Repository(session)
    premium = next(
        (s for s in await repo.list_active_subscriptions(user_id) if s.tier == "premium"),
        None,
    )
    if premium is None or not premium.panel_username:
        raise ValueError("No active premium subscription to switch")

    gateway = panel_gateway or get_panel_gateway()
    panel_user = await gateway.modify_user(
        username=premium.panel_username,
        expire_at=_aware(premium.expires_at),
        traffic_limit_bytes=premium.traffic_limit_bytes,
        device_limit=premium.device_limit,
        status="active",
        inbounds=region_inbounds,
    )
    updated = await repo.update_subscription(
        premium.id,
        region=region,
        subscription_url=panel_user.subscription_url or premium.subscription_url,
    )
    return updated or premium


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
