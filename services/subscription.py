import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings  # kept as a compatibility hook for tests and live monkeypatches
from database.models import Subscription
from database.repository import Repository
from services.panel_gateway import (
    PanelGateway,
    PanelUserNotFoundError,
    get_panel_gateway,
)
from services import subscription_slots as slots
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
    return _to_app_page_url(gateway_url, "happ", auto)


def to_incy_import_url(gateway_url: str | None, auto: bool = False) -> str | None:
    """То же для INCY: страница `/incy/<token>` шлюза открывает `incy://add/...`."""
    return _to_app_page_url(gateway_url, "incy", auto)


def _to_app_page_url(gateway_url: str | None, app: str, auto: bool) -> str | None:
    if not gateway_url or "/sub/" not in gateway_url:
        return None
    page_url = gateway_url.replace("/sub/", f"/{app}/", 1)
    return f"{page_url.rstrip('/')}/auto" if auto else page_url


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


async def _renewal_starts_at(
    repo: Repository,
    latest: Subscription | None,
    now: datetime,
    *,
    paid_renewal: bool,
) -> datetime:
    """Preserve paid time when only the current account's traffic ran out.

    ``is_active`` is availability, not proof that the paid term has expired.
    Other inactive states retain their existing behavior: a disabled or
    superseded subscription must not regain its old term through this path.
    """
    if latest is None or _aware(latest.expires_at) <= now:
        return now
    if latest.is_active:
        return _aware(latest.expires_at)
    if not (
        paid_renewal
        and latest.tier == "standard"
        and (latest.status or "").lower() == "limited"
    ):
        return now

    # The existing "latest" lookup sorts by expiry, not creation order. An
    # older limited row with a long expiry may already have been superseded.
    # Premium was a separate lane; all other rows share this account's lane —
    # within one subscription slot: a newer extra subscription is not a
    # successor of the main one.
    slot = slots.slot_number(getattr(latest, "panel_username", None))
    subscriptions = await repo.list_subscriptions_by_user(latest.user_id)
    if any(
        row.id > latest.id
        and row.tier != "premium"
        and slots.slot_number(getattr(row, "panel_username", None)) == slot
        for row in subscriptions
    ):
        return now
    return _aware(latest.expires_at)


async def _purchase_slot(
    repo: Repository,
    user,
    tariff: Tariff,
    gateway: PanelGateway,
    target: str | None,
) -> tuple[Subscription | None, str, list[Subscription]]:
    """Какую подписку покупают: (последняя запись этого места, имя в панели, записи места).

    Без цели и при чужом или неизвестном номере — основная подписка: оплата
    не должна потеряться из-за номера, который не сходится.
    """
    rows = [
        row
        for row in await repo.list_subscriptions_by_user(user.id)
        if row.tier in ("trial", "standard")
    ]
    base = gateway.build_username(user.telegram_id)

    if target == slots.TARGET_NEW:
        if tariff.tier == "trial":
            raise ValueError("A trial cannot be an extra subscription")
        active = await repo.list_active_subscriptions(user.id)
        if not slots.can_add(active):
            # Оплата уже прошла, поэтому выдаём и сверх лимита: лимит держит бот
            # до выставления счёта, здесь только отмечаем расхождение.
            logger.warning("user %s: extra subscription beyond the limit of %s", user.id, slots.MAX_SUBSCRIPTIONS)
        username = slots.slot_username(base, slots.free_slot_number(active))
        return None, username, [row for row in rows if row.panel_username == username]

    chosen: str | None = None
    if target is not None:
        candidate = await repo.get_subscription(int(target))
        if candidate is not None and candidate.user_id == user.id:
            if slots.is_extra(candidate.panel_username):
                chosen = candidate.panel_username
        else:
            logger.warning("user %s: purchase target %s is not theirs, renewing the main one", user.id, target)

    if chosen is not None:
        slot_rows = [row for row in rows if row.panel_username == chosen]
    else:
        slot_rows = [row for row in rows if not slots.is_extra(row.panel_username)]
    latest = max(slot_rows, key=lambda row: (_aware(row.expires_at), row.id), default=None)
    username = latest.panel_username if latest is not None and latest.panel_username else (chosen or base)
    return latest, username, slot_rows


async def activate_panel_subscription(
    session: AsyncSession,
    user_id: int,
    plan: str,
    panel_gateway: PanelGateway | None = None,
    target: str | None = None,
) -> Subscription:
    tariff: Tariff = resolve_tariff(plan)
    repo = Repository(session)
    user = await repo.get_user(user_id)
    if user is None:
        raise ValueError(f"Unknown user_id: {user_id}")

    now = datetime.now(timezone.utc)
    gateway = panel_gateway or get_panel_gateway()
    latest, panel_username, slot_rows = await _purchase_slot(repo, user, tariff, gateway, target)
    starts_at = await _renewal_starts_at(
        repo, latest, now, paid_renewal=tariff.tier == "standard"
    )

    expires_at = starts_at + timedelta(days=tariff.duration_days)
    # «Без лимита» панель понимает только как 0: пустое значение она при
    # изменении пользователя просто пропускает, и бывший пробник, оплативший
    # безлимит, остался бы со своими 10 ГБ (01.10.2026, services/winback.py).
    panel_traffic_limit = tariff.traffic_limit_bytes if tariff.traffic_limit_bytes is not None else 0

    if await _panel_user_exists(gateway, panel_username):
        panel_user = await gateway.modify_user(
            username=panel_username,
            expire_at=expires_at,
            traffic_limit_bytes=panel_traffic_limit,
            status="active",
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
            traffic_limit_bytes=panel_traffic_limit,
            telegram_id=user.telegram_id,
            status="active",
            description=f"Telegram user {user.telegram_id}",
            traffic_resets_monthly=tariff.traffic_resets_monthly,
        )

    # Гаснут только прежние записи этого же места: основная не трогает
    # дополнительные и наоборот.
    for row in slot_rows:
        if row.is_active:
            await repo.deactivate_subscription(row.id)
    subscription = await repo.create_subscription(
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
    if tariff.tier == "trial":
        await repo.record_funnel_event(user_id, "trial")
    return subscription






async def check_subscription_active(session: AsyncSession, user_id: int) -> bool:
    repo = Repository(session)
    subscription = await repo.get_active_subscription(user_id)
    return subscription is not None


def _device_limit(subscription: Subscription) -> int | None:
    """Сколько устройств обещает тариф этой подписки.

    Источник правды — тариф, а не колонка в базе. Колонка заполнена у четверти
    подписок, у остальных NULL, и последствия были такие: человеку с оплаченным
    тарифом бот показывал «∞ устройств», а выдача считала, что ограничивать его
    не нужно. Сохранённое значение остаётся запасным — для планов, которых в
    тарифах больше нет.
    """

    try:
        return resolve_tariff(subscription.plan).device_limit
    except ValueError:
        return subscription.device_limit


async def get_subscription_info(session: AsyncSession, user_id: int) -> dict[str, object]:
    repo = Repository(session)
    subscription = await repo.get_latest_subscription(user_id)
    if subscription is not None and slots.is_extra(subscription.panel_username):
        # Кабинет и шлюз спрашивают «подписку аккаунта» — это основная, а не
        # последняя купленная дополнительная.
        main_rows = [
            row for row in await repo.list_subscriptions_by_user(user_id)
            if not slots.is_extra(row.panel_username)
        ]
        if main_rows:
            subscription = max(main_rows, key=lambda row: (_aware(row.expires_at), row.id))
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
        "device_limit": _device_limit(subscription),
        "status": subscription.status,
        "started_at": subscription.started_at,
        "expires_at": subscription.expires_at,
    }


# Две выдачи одному клиенту не должны читать один и тот же конец подписки
# (аудит 22.09.2026, BILL-03): вторая ждёт первую и продлевает уже от её срока.
_activate_unlocked = activate_panel_subscription


async def activate_panel_subscription(session: AsyncSession, user_id: int, plan: str, *args, **kwargs) -> Subscription:
    from services.activation_lock import user_activation_lock

    async with user_activation_lock(session, user_id):
        return await _activate_unlocked(session, user_id, plan, *args, **kwargs)
