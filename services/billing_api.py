from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, User
from database.repository import Repository
from services import promo, referral, wallet
from services.money import format_rub
from services.payment import PLANS, create_invoice_payload, normalize_payment_plan_code
from services.subscription import activate_panel_subscription, get_subscription_info
from services.tariffs import PREMIUM_REGIONS, TARIFFS, RegionOption, Tariff, resolve_premium_region, resolve_tariff


@dataclass(frozen=True)
class BillingPlan:
    code: str
    title: str
    tier: str
    duration_days: int
    price_rub: int
    crypto_amount: str
    traffic_limit_bytes: int | None
    device_limit: int | None
    description: str


@dataclass(frozen=True)
class BillingRegion:
    code: str
    title: str
    city: str
    country_code: str
    is_on_demand: bool


@dataclass(frozen=True)
class SubscriptionSnapshot:
    exists: bool
    is_active: bool
    plan: str | None
    plan_title: str | None
    tier: str | None = None
    panel_username: str | None = None
    sub_token: str | None = None
    subscription_url: str | None = None
    traffic_limit_bytes: int | None = None
    traffic_used_bytes: int | None = None
    device_limit: int | None = None
    status: str | None = None
    started_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PaymentIntent:
    user_id: int
    telegram_id: int
    plan: BillingPlan
    region: BillingRegion | None
    payload: str
    amount: str
    amount_minor: int
    asset: str
    description: str


def _plan_from_tariff(tariff: Tariff) -> BillingPlan:
    return BillingPlan(
        code=tariff.code,
        title=tariff.title,
        tier=tariff.tier,
        duration_days=tariff.duration_days,
        price_rub=tariff.price_rub,
        crypto_amount=tariff.crypto_amount,
        traffic_limit_bytes=tariff.traffic_limit_bytes,
        device_limit=tariff.device_limit,
        description=tariff.description,
    )


def _region_from_option(region: RegionOption) -> BillingRegion:
    return BillingRegion(
        code=region.code,
        title=region.title,
        city=region.city,
        country_code=region.country_code,
        is_on_demand=region.is_on_demand,
    )


def _snapshot_from_info(info: dict[str, object]) -> SubscriptionSnapshot:
    return SubscriptionSnapshot(
        exists=bool(info["exists"]),
        is_active=bool(info["is_active"]),
        plan=info.get("plan") if isinstance(info.get("plan"), str) else None,
        plan_title=info.get("plan_title") if isinstance(info.get("plan_title"), str) else None,
        tier=info.get("tier") if isinstance(info.get("tier"), str) else None,
        panel_username=info.get("panel_username") if isinstance(info.get("panel_username"), str) else None,
        sub_token=info.get("sub_token") if isinstance(info.get("sub_token"), str) else None,
        subscription_url=info.get("subscription_url") if isinstance(info.get("subscription_url"), str) else None,
        traffic_limit_bytes=info.get("traffic_limit_bytes") if isinstance(info.get("traffic_limit_bytes"), int) else None,
        traffic_used_bytes=info.get("traffic_used_bytes") if isinstance(info.get("traffic_used_bytes"), int) else None,
        device_limit=info.get("device_limit") if isinstance(info.get("device_limit"), int) else None,
        status=info.get("status") if isinstance(info.get("status"), str) else None,
        started_at=info.get("started_at") if isinstance(info.get("started_at"), datetime) else None,
        expires_at=info.get("expires_at") if isinstance(info.get("expires_at"), datetime) else None,
    )


def crypto_minor_units(amount: str) -> int:
    return int((Decimal(amount) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def list_billing_plans(*, tier: str | None = None, include_trial: bool = False) -> list[BillingPlan]:
    plans: list[BillingPlan] = []
    for tariff in sorted(TARIFFS.values(), key=lambda item: (item.sort_order, item.code)):
        if not include_trial and tariff.code == "trial":
            continue
        if tier is not None and tariff.tier != tier:
            continue
        plans.append(_plan_from_tariff(tariff))
    return plans


def get_billing_plan(code: str) -> BillingPlan:
    plan_code = normalize_payment_plan_code(code)
    return _plan_from_tariff(resolve_tariff(plan_code))


def list_billing_regions() -> list[BillingRegion]:
    return [
        _region_from_option(region)
        for region in sorted(PREMIUM_REGIONS.values(), key=lambda item: (item.title, item.code))
    ]


async def get_subscription_snapshot(session: AsyncSession, user_id: int) -> SubscriptionSnapshot:
    return _snapshot_from_info(await get_subscription_info(session, user_id))


async def activate_access(
    session: AsyncSession,
    user_id: int,
    plan: str,
    *,
    panel_client: object | None = None,
    panel_gateway: object | None = None,
) -> SubscriptionSnapshot:
    await activate_panel_subscription(
        session,
        user_id,
        plan,
        panel_client=panel_client,
        panel_gateway=panel_gateway,
    )
    return await get_subscription_snapshot(session, user_id)


async def build_payment_intent(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    plan: str,
    region: str | None = None,
    asset: str = "USDT",
) -> PaymentIntent:
    tariff = resolve_tariff(normalize_payment_plan_code(plan))
    billing_plan = _plan_from_tariff(tariff)
    billing_region: BillingRegion | None = None

    if tariff.tier == "premium":
        if region is None:
            raise ValueError("Premium plan requires region")
        billing_region = _region_from_option(resolve_premium_region(region))
    elif region is not None:
        raise ValueError("Region is only supported for premium plans")

    repo = Repository(session)
    user = await repo.get_or_create_user(telegram_id=telegram_id, username=username)
    payload = create_invoice_payload(
        user_id=user.id,
        plan=billing_plan.code,
        region=billing_region.code if billing_region else None,
    )
    amount = str(PLANS[billing_plan.code]["crypto_amount"])
    description = billing_plan.description
    if billing_region is not None:
        description = f"{description}: {billing_region.title}"

    return PaymentIntent(
        user_id=user.id,
        telegram_id=user.telegram_id,
        plan=billing_plan,
        region=billing_region,
        payload=payload,
        amount=amount,
        amount_minor=crypto_minor_units(amount),
        asset=asset,
        description=description,
    )


async def register_cryptobot_payment(
    session: AsyncSession,
    *,
    intent: PaymentIntent,
    external_invoice_id: str,
) -> Payment:
    repo = Repository(session)
    return await repo.create_cryptobot_payment(
        user_id=intent.user_id,
        amount=intent.amount_minor,
        external_invoice_id=external_invoice_id,
        invoice_payload=intent.payload,
        plan=intent.plan.code,
    )


async def register_yookassa_payment(
    session: AsyncSession,
    *,
    intent: PaymentIntent,
    external_payment_id: str,
) -> Payment:
    """Store a pending YooKassa payment in RUB kopecks, keyed by its payment id."""
    repo = Repository(session)
    return await repo.create_yookassa_payment(
        user_id=intent.user_id,
        amount=intent.plan.price_rub * 100,
        external_invoice_id=external_payment_id,
        invoice_payload=intent.payload,
        plan=intent.plan.code,
    )


# ---------------------------------------------------------------------------
# Shared account surface (bot + website)
#
# These thin wrappers and the composite ``AccountOverview`` give both the
# Telegram bot and the future Next.js cabinet a single import surface for
# wallet, referral and promo operations. Transport (HTTP handlers for the
# site) is layered on top of these functions, not the underlying services.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountOverview:
    user_id: int
    telegram_id: int
    subscription: SubscriptionSnapshot
    wallet: wallet.WalletSnapshot
    balance_display: str
    referral: referral.ReferralStats


async def get_account_overview(
    session: AsyncSession,
    user_id: int,
    *,
    wallet_history_limit: int = 10,
) -> AccountOverview:
    repo = Repository(session)
    user = await repo.get_user(user_id)
    if user is None:
        raise ValueError(f"Unknown user_id: {user_id}")

    subscription = await get_subscription_snapshot(session, user_id)
    wallet_snapshot = await wallet.get_wallet_snapshot(
        session, user_id, history_limit=wallet_history_limit
    )
    referral_stats = await referral.get_referral_stats(session, user_id)
    return AccountOverview(
        user_id=user_id,
        telegram_id=user.telegram_id,
        subscription=subscription,
        wallet=wallet_snapshot,
        balance_display=format_rub(wallet_snapshot.balance_kopecks),
        referral=referral_stats,
    )


async def get_wallet(
    session: AsyncSession,
    user_id: int,
    *,
    history_limit: int = 20,
) -> wallet.WalletSnapshot:
    return await wallet.get_wallet_snapshot(session, user_id, history_limit=history_limit)


async def redeem_balance_promo(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
) -> promo.PromoRedemptionResult:
    return await promo.redeem_balance_promo(session, user_id=user_id, code=code)


async def preview_checkout_discount(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
    amount_kopecks: int,
) -> promo.DiscountResult:
    return await promo.preview_discount(
        session, user_id=user_id, code=code, amount_kopecks=amount_kopecks
    )


async def get_referral_overview(session: AsyncSession, user_id: int) -> referral.ReferralStats:
    return await referral.get_referral_stats(session, user_id)


async def attach_referral_code(
    session: AsyncSession,
    *,
    user_id: int,
    ref_code: str,
) -> User:
    return await referral.attach_referrer(session, user_id=user_id, ref_code=ref_code)


async def reward_referral_for_payment(
    session: AsyncSession,
    *,
    paid_user_id: int,
    plan_code: str,
    payment_reference: str,
) -> wallet.WalletEntry | None:
    return await referral.reward_referrer_for_payment(
        session,
        paid_user_id=paid_user_id,
        plan_code=plan_code,
        payment_reference=payment_reference,
    )
