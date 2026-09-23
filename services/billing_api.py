from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, Subscription, User, WalletTransaction
from database.repository import Repository
from services import promo, referral
from services.money import format_rub
from services.payment import create_invoice_payload, normalize_payment_plan_code
from services.subscription import activate_panel_subscription, get_subscription_info
from services.tariffs import TARIFFS, Tariff, resolve_tariff


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
    payload: str
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




async def get_subscription_snapshot(session: AsyncSession, user_id: int) -> SubscriptionSnapshot:
    return _snapshot_from_info(await get_subscription_info(session, user_id))


async def activate_access(
    session: AsyncSession,
    user_id: int,
    plan: str,
    *,
    panel_gateway: object | None = None,
) -> SubscriptionSnapshot:
    await activate_panel_subscription(
        session,
        user_id,
        plan,
        panel_gateway=panel_gateway,
    )
    return await get_subscription_snapshot(session, user_id)


async def build_payment_intent(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    plan: str,
    target: str | None = None,
) -> PaymentIntent:
    """``target`` — какую подписку покупают (services/subscription_slots.py)."""
    tariff = resolve_tariff(normalize_payment_plan_code(plan))
    billing_plan = _plan_from_tariff(tariff)

    repo = Repository(session)
    user = await repo.get_or_create_user(telegram_id=telegram_id, username=username)
    payload = create_invoice_payload(
        user_id=user.id,
        plan=billing_plan.code,
        target=target,
    )

    return PaymentIntent(
        user_id=user.id,
        telegram_id=user.telegram_id,
        plan=billing_plan,
        payload=payload,
        description=billing_plan.description,
    )


def _subscription_credential(link: str | None) -> str | None:
    """Extract the entire opaque credential, without treating it as verified."""
    raw = (link or "").strip().split("?", 1)[0].split("#", 1)[0]
    if not raw or len(raw) > 512:
        return None
    segments = [part for part in raw.rstrip("/").split("/") if part]
    if not segments:
        return None
    if segments[-1] in {"auto", "hy2", "split"}:
        segments.pop()
    if not segments:
        return None
    credential = segments[-1]
    # ASCII-only also keeps compare_digest safe for untrusted input. Preserve
    # legacy base64 padding as well as the panel's URL-safe signed format.
    if not re.fullmatch(r"[A-Za-z0-9_+=-]{8,256}", credential):
        return None
    if _decode_panel_username(credential) is None:
        return None
    return credential


def subscription_token(link: str | None) -> str | None:
    """Unverified panel-username lookup hint, never proof of account ownership.

    Host aliases and known subscription flavors may differ. Authorization must
    compare the entire credential with the latest trusted stored subscription
    URL; decoding the public username alone does not authenticate a customer.
    """
    credential = _subscription_credential(link)
    return _decode_panel_username(credential) if credential is not None else None


def _decode_panel_username(token: str) -> str | None:
    """Unverified panel username out of a subscription token.

    The token is base64 of `<panel-username>,<issued-at>` with a signature
    appended raw, so it does not decode as a whole. The longest decodable
    prefix is what carries the name. This does not check the signature and must
    only be used as a lookup hint before full credential verification.
    """
    if not token or len(token) > 256:
        return None
    for length in range(len(token), 7, -1):
        if length % 4 == 1:  # never a valid base64 length
            continue
        try:
            decoded = base64.b64decode(token[:length] + "===", validate=False)
        except Exception:  # noqa: BLE001
            continue
        name = decoded.decode("utf-8", "replace").split(",", 1)[0].strip()
        # Panel usernames are `tg_<id>`; anything else was not one of our links.
        if re.fullmatch(r"tg_-?\d{1,20}", name):
            return name
    return None


async def build_web_payment_intent(
    session: AsyncSession,
    *,
    plan: str,
    telegram_id: int | None = None,
    username: str | None = None,
    email: str | None = None,
    subscription_link: str | None = None,
) -> PaymentIntent:
    """Payment intent for a website checkout.

    Authenticated buyers share their existing Telegram or website account; the
    caller must derive telegram_id from a verified session, never public input.
    New email-only buyers
    get a local account under a synthetic NEGATIVE telegram_id — real Telegram
    ids are positive, so the sign marks "no Telegram chat behind this user"
    and delivery code must not DM it.

    A buyer can renew using the full credential in their subscription link.
    The decoded username is not authentication. An email address on its own
    must never select an existing account or change its owner details.
    """
    clean_email = (email or "").strip().lower() or None
    linked_credential = _subscription_credential(subscription_link)
    linked_token = subscription_token(subscription_link)
    if subscription_link and linked_credential is None:
        raise ValueError("invalid_subscription")
    if telegram_id is None and clean_email is None and linked_token is None:
        raise ValueError("telegram_id or email is required")

    repo = Repository(session)
    if linked_token is not None:
        subscription = await repo.get_subscription_by_token(linked_token)
        if subscription is None:
            raise ValueError("unknown_subscription")
        stored_credential = _subscription_credential(subscription.subscription_url)
        if (
            stored_credential is None
            or linked_credential is None
            or not secrets.compare_digest(linked_credential, stored_credential)
        ):
            raise ValueError("unknown_subscription")
        owner = await repo.get_user(subscription.user_id)
        if owner is None:
            raise ValueError("unknown_subscription")
        if telegram_id is not None and telegram_id != owner.telegram_id:
            raise ValueError("subscription_account_mismatch")
        telegram_id = owner.telegram_id
        # Possession of a subscription link permits renewal, not rewriting the
        # owner's profile. Shared family links must not reassign that account.
        username = owner.username
    created_guest = False
    if telegram_id is None:
        from services.web_accounts import site_account_by_email

        user = await site_account_by_email(session, clean_email)
        if user is None:
            user = await repo.create_user(telegram_id=-(secrets.randbits(52) + 1))
            created_guest = True
        elif not await _is_unpaid_guest(session, user):
            raise ValueError("authentication_required")
        # An unpaid guest is this address's own earlier attempt: buying onto it
        # hands over nothing but what the buyer is paying for right now.
        telegram_id = user.telegram_id
    else:
        existing = await repo.get_user_by_telegram_id(telegram_id)
        if existing is not None and username is None:
            # A site checkout knows no Telegram username; keep the stored one
            # instead of letting get_or_create_user null it out.
            username = existing.username

    intent = await build_payment_intent(
        session, telegram_id=telegram_id, username=username, plan=plan
    )
    # Checkout contact is not an account-email change operation. Existing
    # accounts use the authenticated profile flow to update their email.
    if created_guest and clean_email is not None:
        await repo.update_user(intent.user_id, email=clean_email)
    return intent


class WebAuthError(Exception):
    """Raised for site email/password auth failures with a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def _is_unpaid_guest(session: AsyncSession, user: User) -> bool:
    """A site guest whose checkout never went through.

    Checkout creates the account before the buyer pays, so walking away from the
    payment page leaves one behind: an address, no password, nothing bought.
    It holds nothing an address could be used to claim, so it must not lock that
    address out of buying again or registering (17.09.2026 a buyer was).
    """
    if user.telegram_id >= 0 or user.web_password_hash or user.balance:
        return False
    holds_anything = await session.scalar(
        select(
            exists().where(Subscription.user_id == user.id)
            | exists().where(
                Payment.user_id == user.id, Payment.status.notin_(("pending", "canceled"))
            )
            | exists().where(WalletTransaction.user_id == user.id)
        )
    )
    return not holds_anything


async def _checkout_may_still_pay(session: AsyncSession, user: User) -> bool:
    """Whether a pending checkout of this account can still bring money in.

    Providers cancel abandoned checkouts without telling us, so a pending row
    proves nothing; YooKassa is asked directly. Anything unclear counts as live.
    """
    from services import yookassa

    pending = await session.scalars(
        select(Payment).where(Payment.user_id == user.id, Payment.status == "pending")
    )
    repo = Repository(session)
    for payment in list(pending):
        if payment.provider != "yookassa" or not payment.external_invoice_id:
            return True
        try:
            remote = await yookassa.get_payment(str(payment.external_invoice_id))
        except Exception:  # noqa: BLE001 - unreachable provider: assume it may pay
            return True
        if str(remote.get("status") or "").strip().lower() != "canceled":
            return True
        await repo.update_payment_status(payment.id, "canceled")
    return False


async def _email_account_telegram_id() -> int:
    # Email accounts have no Telegram chat: a synthetic negative id marks them so
    # delivery code never DMs them (real Telegram ids are positive).
    return -(secrets.randbits(52) + 1)


async def register_web_account(session: AsyncSession, *, email: str, password: str) -> int:
    """Create a new site account for email+password. Returns its telegram_id.

    An existing passwordless guest account requires verified recovery; knowing
    its email is not sufficient to attach a password or claim past purchases.
    Raises WebAuthError without modifying an existing account.

    The one exception is a guest an unpaid checkout left behind: there is nothing
    to claim, so registration takes it over — once no checkout of it can still pay.
    """
    from services import webauth

    clean_email = (email or "").strip().lower()
    if not clean_email:
        raise WebAuthError("invalid_email")
    if not webauth.is_password_acceptable(password or ""):
        raise WebAuthError("weak_password")

    from services import web_checkout
    from services.web_accounts import site_account_by_email

    repo = Repository(session)
    # Почта для чеков у Telegram-аккаунта не занимает логин (аудит 22.09, SEC-03).
    existing = await site_account_by_email(session, clean_email)
    if existing is not None and not await _is_unpaid_guest(session, existing):
        raise WebAuthError("already_registered")
    if await web_checkout.may_still_pay(session, clean_email):
        # Оплата по этой почте ещё идёт: аккаунт создаст она сама, а чужая
        # регистрация на эту почту иначе перехватила бы её.
        raise WebAuthError("payment_in_progress")
    if existing is not None:
        if await _checkout_may_still_pay(session, existing):
            raise WebAuthError("payment_in_progress")
        await repo.update_user(existing.id, web_password_hash=webauth.hash_password(password))
        return existing.telegram_id

    password_hash = webauth.hash_password(password)
    user = await repo.create_user(telegram_id=await _email_account_telegram_id())
    await repo.update_user(user.id, email=clean_email, web_password_hash=password_hash)
    return user.telegram_id


async def set_web_password_by_subscription(
    session: AsyncSession, *, subscription_link: str, password: str, email: str | None = None
) -> int:
    """Verified recovery: prove ownership with the link, then set a password.

    This is the "verified recovery" ``register_web_account`` refuses to do on an
    email alone. Half of our website buyers checked out as guests and hold an
    account with no password at all: they cannot sign in, and registering with
    their own address is rejected — correctly, since an address is public and
    accepting one would hand the account to whoever guesses it.

    The subscription link is different. It carries a credential the panel signed,
    the renewal path already treats it as proof, and the customer holds it in
    their app. One use of it buys a durable password; the link never becomes a
    standing key to the cabinet, which also shows the owner's email address.

    An account that already has a password is left untouched — otherwise a
    forwarded link (people send them to their children) would be a takeover.
    """
    from services import webauth

    if not webauth.is_password_acceptable(password or ""):
        raise WebAuthError("weak_password")

    credential = _subscription_credential(subscription_link)
    token = subscription_token(subscription_link)
    if credential is None or token is None:
        raise WebAuthError("invalid_subscription")

    repo = Repository(session)
    subscription = await repo.get_subscription_by_token(token)
    if subscription is None:
        raise WebAuthError("invalid_subscription")
    stored = _subscription_credential(subscription.subscription_url)
    # Fast path first; otherwise the panel decides. It reissues tokens, so the
    # link a customer holds routinely differs from the one we stored last.
    if stored is None or not secrets.compare_digest(credential, stored):
        from services import sub_token

        if not await sub_token.token_is_genuine(credential):
            # Same answer as an unknown subscription, so the endpoint cannot be
            # used to probe which links exist.
            raise WebAuthError("invalid_subscription")

    user = await repo.get_user(subscription.user_id)
    if user is None:
        raise WebAuthError("invalid_subscription")
    if user.telegram_id > 0:
        # Ссылку подписки пересылают родным, а Telegram-аккаунт входит через
        # Telegram: пересланная ссылка не должна открывать чужой кабинет
        # (аудит 22.09.2026, SEC-02).
        raise WebAuthError("telegram_account")
    if user.web_password_hash:
        raise WebAuthError("password_already_set")

    clean_email = (email or "").strip().lower() or None
    if clean_email and clean_email != (user.email or "").strip().lower():
        # A second account already holding that address would collide on login.
        from services.web_accounts import site_account_by_email

        other = await site_account_by_email(session, clean_email)
        if other is not None and other.id != user.id:
            raise WebAuthError("email_taken")

    fields = {"web_password_hash": webauth.hash_password(password)}
    if clean_email and not user.email:
        fields["email"] = clean_email
    await repo.update_user(user.id, **fields)
    await session.commit()
    return user.telegram_id


async def authenticate_web_account(session: AsyncSession, *, email: str, password: str) -> int | None:
    """Verify email+password; return the account's telegram_id or None."""
    from services import webauth

    clean_email = (email or "").strip().lower()
    if not clean_email or not password:
        return None
    from services.web_accounts import login_account_by_email

    user = await login_account_by_email(session, clean_email)
    if user is None or not webauth.verify_password(password, user.web_password_hash):
        return None
    return user.telegram_id


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
# referral and promo operations. Transport (HTTP handlers for the
# site) is layered on top of these functions, not the underlying services.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountOverview:
    user_id: int
    telegram_id: int
    subscription: SubscriptionSnapshot
    referral: referral.ReferralStats
    email: str | None = None


async def get_account_overview(session: AsyncSession, user_id: int) -> AccountOverview:
    repo = Repository(session)
    user = await repo.get_user(user_id)
    if user is None:
        raise ValueError(f"Unknown user_id: {user_id}")

    subscription = await get_subscription_snapshot(session, user_id)
    referral_stats = await referral.get_referral_stats(session, user_id)
    return AccountOverview(
        user_id=user_id,
        telegram_id=user.telegram_id,
        subscription=subscription,
        referral=referral_stats,
        email=user.email,
    )


async def redeem_promo(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
    panel_gateway: object | None = None,
) -> promo.PromoRedemptionResult:
    """Redeem a subscription-grant code, provisioning the access it promises.

    A grant goes down the same path a paid order takes, so the user ends up with
    a working config rather than a promise of one. Discount codes are a separate
    entry point (they apply at checkout, not on redemption)."""
    result = await promo.redeem_subscription_promo(session, user_id=user_id, code=code)
    await activate_access(
        session,
        user_id,
        result.plan,
        panel_gateway=panel_gateway,
    )
    return result


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
