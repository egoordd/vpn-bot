from __future__ import annotations

import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database.repository import Repository
from services import billing_api, moynalog, promo, tribute, yookassa
from services.billing_api import AccountOverview, BillingPlan, SubscriptionSnapshot
from services.payment import parse_invoice_payload_details
from services.referral import normalize_source_slug, ReferralStats
from services.subscription import activate_panel_subscription, to_gateway_subscription_url
from services.tariffs import resolve_tariff

# HTTP transport over services/billing_api.py (Phase 3, item 32/33).
# The Next.js site is the only intended consumer; responses use the camelCase
# contract from web/src/lib/billing/types.ts. Run locally with:
#   uvicorn services.http_api:app --port 8001


class PromoPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: int = Field(alias="userId", gt=0)
    code: str = Field(min_length=1, max_length=64)
    amount_kopecks: int = Field(alias="amountKopecks", gt=0, le=100_000_000)


_WEB_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Abuse limits for the unauthenticated site checkout. The per-identity cap is the
# one that actually stops abuse: it counts a single buyer, by email or Telegram
# id, and one person never needs six payment intents an hour.
#
# The per-IP cap is deliberately loose, because on this market an address is not
# a person. Russian mobile carriers put thousands of subscribers behind one
# CGNAT address, so a burst of buyers arriving from an ad on MTS or Beeline
# shares a single public IP. At the old ceiling of eight per ten minutes an
# ordinary campaign spike would have started returning 429 to real customers,
# who do not write to support — they just leave. It still caps a scripted flood,
# which is all it was ever there for.
_CHECKOUT_IP_LIMIT = 40
_CHECKOUT_IP_WINDOW = 600  # 10 min
_CHECKOUT_ID_LIMIT = 5
_CHECKOUT_ID_WINDOW = 3600  # 1 h


async def _tag_source(session: AsyncSession, user_id: int, raw: str | None) -> None:
    """Записать канал привлечения при первом касании.

    Ставится только если ещё не заполнен: человек может вернуться по другой
    ссылке, но привёл его первый канал, и отчёт должен показывать именно его.
    """
    slug = normalize_source_slug(raw)
    if not slug:
        return
    try:
        await Repository(session).set_user_source_if_unset(user_id, slug)
    except Exception:  # noqa: BLE001 - телеметрия не должна ломать покупку
        logging.getLogger("funnel").exception("Could not tag source for user_id=%s", user_id)


def _client_ip(request: Request) -> str:
    # Next forwards the browser IP as x-client-ip; fall back to the socket peer.
    forwarded = request.headers.get("x-client-ip") or request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip()
    if ip:
        return ip
    return request.client.host if request.client else "unknown"


async def _rate_limit_ok(redis: Any, bucket: str, key: str, limit: int, window: int) -> bool:
    """Fixed-window counter in Redis. Fails OPEN when Redis is absent so a cache
    outage can never block real purchases."""
    if redis is None or not key:
        return True
    redis_key = f"rl:{bucket}:{key}"
    try:
        count = await redis.incr(redis_key)
        if count == 1:
            await redis.expire(redis_key, window)
        return count <= limit
    except Exception:
        return True


# Site session IDs are either real positive Telegram IDs or negative synthetic
# email-account IDs. Keep them exactly representable in the browser and never
# accept zero/bools/coerced strings as an account identity. Authentication is
# enforced by the internal API bearer and the site's signed session, not by ID.
_MAX_WEB_ACCOUNT_ID = (1 << 53) - 1


def _nonzero_web_account_id(value: int | None) -> int | None:
    if value == 0:
        raise ValueError("account ID must not be zero")
    return value


class WebCheckoutRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plan: str = Field(min_length=1, max_length=64)
    telegram_id: int | None = Field(
        default=None, alias="telegramId", strict=True,
        ge=-_MAX_WEB_ACCOUNT_ID, le=_MAX_WEB_ACCOUNT_ID,
    )
    email: str | None = Field(default=None, max_length=320)
    # A customer whose subscription lapsed cannot open Telegram in Russia, so
    # the link already in their VPN app is how they say which account is theirs.
    subscription: str | None = Field(default=None, max_length=512)
    source: str | None = Field(default=None, max_length=64)

    _validate_account_id = field_validator("telegram_id")(_nonzero_web_account_id)


class WebPromoRedeemRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    telegram_id: int = Field(alias="telegramId")
    code: str = Field(min_length=1, max_length=64)


class WebEmailUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Keep the existing Telegram-only receipt-email flow. For web accounts this
    # field is also the login identifier; a verified email-change flow is
    # required before allowing negative IDs here. Checkout supports both signs.
    telegram_id: int = Field(
        alias="telegramId", strict=True, gt=0, le=_MAX_WEB_ACCOUNT_ID,
    )
    email: str = Field(min_length=3, max_length=320)

    _validate_account_id = field_validator("telegram_id")(_nonzero_web_account_id)


class WebRecoverRequest(BaseModel):
    """Verified recovery for a buyer who has a subscription but no password."""

    model_config = ConfigDict(populate_by_name=True)

    subscription: str = Field(min_length=8, max_length=512, alias="subscriptionLink")
    password: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)


class WebAttachTelegramRequest(BaseModel):
    """Join a website account into the Telegram account of the same person.

    Both ids come from the caller's own verification — the session cookie and a
    signed Telegram login payload — never from anything the browser typed.
    """

    model_config = ConfigDict(populate_by_name=True)

    web_telegram_id: int = Field(alias="webTelegramId")
    telegram_id: int = Field(alias="telegramId")
    username: str | None = Field(default=None, max_length=64)


class WebAuthRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)
    # Кампания, по ссылке которой человек пришёл на сайт (кука unlock_src,
    # её ставит /go/<кампания>). Нормализуется так же, как src_-деплинк бота,
    # чтобы одна кампания не расщепилась на две строки в отчёте.
    source: str | None = Field(default=None, max_length=64)


class ReceiptCompleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receipt_url: str = Field(alias="receiptUrl", min_length=1, max_length=512)


class WebTrialRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Site accounts include email-only buyers with synthetic negative ids.
    telegram_id: int = Field(alias="telegramId")


class LinkClickRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    campaign: str = Field(min_length=1, max_length=32)
    target: str = Field(default="bot", max_length=16)


_AUTH_IP_LIMIT = 10
_AUTH_IP_WINDOW = 600  # 10 min


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _plan_payload(plan: BillingPlan) -> dict[str, Any]:
    return {
        "code": plan.code,
        "title": plan.title,
        "tier": plan.tier,
        "durationDays": plan.duration_days,
        "priceRub": plan.price_rub,
        "cryptoAmount": plan.crypto_amount,
        "trafficLimitBytes": plan.traffic_limit_bytes,
        "deviceLimit": plan.device_limit,
        "description": plan.description,
    }




def _subscription_payload(sub: SubscriptionSnapshot) -> dict[str, Any]:
    return {
        "exists": sub.exists,
        "isActive": sub.is_active,
        "plan": sub.plan,
        "planTitle": sub.plan_title,
        "tier": sub.tier,
        "subscriptionUrl": sub.subscription_url,
        "trafficLimitBytes": sub.traffic_limit_bytes,
        "trafficUsedBytes": sub.traffic_used_bytes,
        "deviceLimit": sub.device_limit,
        "status": sub.status,
        "expiresAt": _iso(sub.expires_at),
    }


def _referral_payload(stats: ReferralStats) -> dict[str, Any]:
    return {
        "refCode": stats.ref_code,
        "referralsCount": stats.referrals_count,
    }


def _account_payload(account: AccountOverview) -> dict[str, Any]:
    return {
        "userId": account.user_id,
        "telegramId": account.telegram_id,
        "subscription": _subscription_payload(account.subscription),
        "referral": _referral_payload(account.referral),
        "email": account.email,
    }


def _discount_payload(result: promo.DiscountResult) -> dict[str, Any]:
    return {
        "code": result.code,
        "originalKopecks": result.original_kopecks,
        "discountKopecks": result.discount_kopecks,
        "finalKopecks": result.final_kopecks,
    }


_PROMO_STATUS: tuple[tuple[type[promo.PromoError], int, str], ...] = (
    (promo.PromoNotFoundError, 404, "promo_not_found"),
    (promo.PromoMinAmountError, 400, "promo_min_amount"),
    (promo.PromoTypeError, 400, "promo_wrong_type"),
    (promo.PromoExpiredError, 409, "promo_expired"),
    (promo.PromoInactiveError, 409, "promo_inactive"),
    (promo.PromoExhaustedError, 409, "promo_exhausted"),
    (promo.PromoUserLimitError, 409, "promo_user_limit"),
)


def _promo_http_error(exc: promo.PromoError) -> HTTPException:
    for exc_type, status, code in _PROMO_STATUS:
        if isinstance(exc, exc_type):
            return HTTPException(status_code=status, detail=code)
    return HTTPException(status_code=400, detail="promo_error")


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    from config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    application.state.session_pool = async_sessionmaker(engine, expire_on_commit=False)
    application.state.api_token = settings.BILLING_API_TOKEN.get_secret_value()
    application.state.redis = None
    if settings.REDIS_URL:
        import redis.asyncio as aioredis

        application.state.redis = aioredis.from_url(settings.REDIS_URL)
    try:
        yield
    finally:
        if application.state.redis is not None:
            await application.state.redis.aclose()
        await engine.dispose()


async def _get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_pool = request.app.state.session_pool
    async with session_pool() as session:
        yield session


async def _require_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    # Payment webhooks authenticate on their own terms, not the bearer token:
    # Tribute via its HMAC signature, YooKassa by re-fetching the payment from
    # the YooKassa API. Both are exempt from this app-wide bearer check.
    if request.url.path in ("/tribute/webhook", "/yookassa/webhook"):
        return
    expected = getattr(request.app.state, "api_token", "")
    if not expected:
        # Fail CLOSED: a missing/empty token must never expose every account,
        # subscription link, balance and /admin route to the public. (An empty
        # .env has clobbered other vars before — never let that open the API.)
        raise HTTPException(status_code=503, detail="api auth not configured")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="unauthorized")


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


def create_app() -> FastAPI:
    application = FastAPI(
        title="UnLock Billing API",
        version="0.1.0",
        lifespan=_lifespan,
        dependencies=[Depends(_require_auth)],
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/plans")
    async def plans(tier: str | None = None) -> dict[str, Any]:
        items = billing_api.list_billing_plans(tier=tier)
        return {"plans": [_plan_payload(plan) for plan in items]}


    @application.get("/account/{user_id}")
    async def account(user_id: int, session: SessionDep) -> dict[str, Any]:
        try:
            overview = await billing_api.get_account_overview(session, user_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="user_not_found")
        return _account_payload(overview)

    @application.post("/promo/preview")
    async def promo_preview(body: PromoPreviewRequest, session: SessionDep) -> dict[str, Any]:
        try:
            result = await billing_api.preview_checkout_discount(
                session,
                user_id=body.user_id,
                code=body.code,
                amount_kopecks=body.amount_kopecks,
            )
        except promo.PromoError as exc:
            raise _promo_http_error(exc)
        return _discount_payload(result)

    @application.post("/web/promo/redeem")
    async def web_promo_redeem(body: WebPromoRedeemRequest, session: SessionDep) -> dict[str, Any]:
        """Redeem a promo for a site visitor, exactly as the bot redeems it.

        The site used to only *preview a discount*, which no code we sell has
        ever been: every live code grants a subscription, so the cabinet
        answered "промокод не найден" to perfectly valid codes. Redemption is
        the operation people actually want.
        """
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(body.telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        try:
            result = await billing_api.redeem_promo(session, user_id=user.id, code=body.code)
        except promo.PromoError as exc:
            raise _promo_http_error(exc)
        return {
            "code": result.code,
            "kind": result.kind,
            "grantedDays": result.granted_days,
        }

    @application.get("/web/account/by-telegram/{telegram_id}")
    async def web_account_by_telegram(telegram_id: int, session: SessionDep) -> dict[str, Any]:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        try:
            overview = await billing_api.get_account_overview(session, user.id)
        except ValueError:
            raise HTTPException(status_code=404, detail="user_not_found")
        payload = _account_payload(overview)
        # The site shows the multi-protocol gateway link, not the raw panel URL.
        payload["subscription"]["subscriptionUrl"] = to_gateway_subscription_url(
            overview.subscription.subscription_url
        )
        return payload

    @application.post("/web/account/email")
    async def web_account_email(body: WebEmailUpdateRequest, session: SessionDep) -> dict[str, Any]:
        email = body.email.strip().lower()
        if not _WEB_EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="invalid_email")
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(body.telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        await repo.update_user(user.id, email=email)
        return {"ok": True, "email": email}

    @application.post("/web/auth/register")
    async def web_auth_register(body: WebAuthRequest, request: Request, session: SessionDep) -> dict[str, Any]:
        redis = getattr(request.app.state, "redis", None)
        if not await _rate_limit_ok(redis, "auth:ip", _client_ip(request), _AUTH_IP_LIMIT, _AUTH_IP_WINDOW):
            raise HTTPException(status_code=429, detail="rate_limited")
        email = body.email.strip().lower()
        if not _WEB_EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="invalid_email")
        try:
            telegram_id = await billing_api.register_web_account(
                session, email=email, password=body.password
            )
        except billing_api.WebAuthError as exc:
            status = 409 if exc.code == "already_registered" else 400
            raise HTTPException(status_code=status, detail=exc.code)
        user = await Repository(session).get_user_by_telegram_id(telegram_id)
        if user is not None:
            await _tag_source(session, user.id, body.source)
        return {"ok": True, "telegramId": telegram_id}

    @application.post("/web/auth/recover")
    async def web_auth_recover(
        body: WebRecoverRequest, request: Request, session: SessionDep
    ) -> dict[str, Any]:
        """Turn one use of a subscription link into a password on that account.

        Rate limited like the other auth routes: the link carries a signed
        credential, but the endpoint still must not become an oracle for probing
        which links exist.
        """
        redis = getattr(request.app.state, "redis", None)
        if not await _rate_limit_ok(
            redis, "auth:ip", _client_ip(request), _AUTH_IP_LIMIT, _AUTH_IP_WINDOW
        ):
            raise HTTPException(status_code=429, detail="rate_limited")
        email = (body.email or "").strip().lower() or None
        if email and not _WEB_EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="invalid_email")
        try:
            telegram_id = await billing_api.set_web_password_by_subscription(
                session,
                subscription_link=body.subscription,
                password=body.password,
                email=email,
            )
        except billing_api.WebAuthError as exc:
            status = 409 if exc.code in {"password_already_set", "email_taken"} else 400
            raise HTTPException(status_code=status, detail=exc.code)
        return {"ok": True, "telegramId": telegram_id}

    @application.post("/web/account/attach-telegram")
    async def web_account_attach_telegram(
        body: WebAttachTelegramRequest, session: SessionDep
    ) -> dict[str, Any]:
        from services.account_link import attach_telegram_to_web_account

        surviving = await attach_telegram_to_web_account(
            session,
            web_telegram_id=body.web_telegram_id,
            telegram_id=body.telegram_id,
            username=body.username,
        )
        return {"ok": True, "telegramId": surviving}

    @application.post("/web/auth/login")
    async def web_auth_login(body: WebAuthRequest, request: Request, session: SessionDep) -> dict[str, Any]:
        redis = getattr(request.app.state, "redis", None)
        if not await _rate_limit_ok(redis, "auth:ip", _client_ip(request), _AUTH_IP_LIMIT, _AUTH_IP_WINDOW):
            raise HTTPException(status_code=429, detail="rate_limited")
        telegram_id = await billing_api.authenticate_web_account(
            session, email=body.email.strip().lower(), password=body.password
        )
        if telegram_id is None:
            raise HTTPException(status_code=401, detail="invalid_credentials")
        return {"ok": True, "telegramId": telegram_id}

    @application.post("/web/checkout")
    async def web_checkout(body: WebCheckoutRequest, request: Request, session: SessionDep) -> dict[str, Any]:
        from config import get_settings

        email = (body.email or "").strip().lower() or None
        link = (body.subscription or "").strip() or None
        linked = billing_api.subscription_token(link) if link else None
        if link and linked is None:
            raise HTTPException(status_code=400, detail="invalid_subscription")
        if body.telegram_id is None and email is None and linked is None:
            raise HTTPException(status_code=400, detail="identity_required")
        if email is not None and not _WEB_EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="invalid_email")

        # Abuse guard: the site checkout is unauthenticated, and each call mints a
        # real user row + a real YooKassa payment. Cap per IP and per identity.
        redis = getattr(request.app.state, "redis", None)
        ip = _client_ip(request)
        identity = email or (str(body.telegram_id) if body.telegram_id else "") or (linked or "")
        allowed = await _rate_limit_ok(redis, "checkout:ip", ip, _CHECKOUT_IP_LIMIT, _CHECKOUT_IP_WINDOW)
        if allowed:
            allowed = await _rate_limit_ok(
                redis, "checkout:id", identity, _CHECKOUT_ID_LIMIT, _CHECKOUT_ID_WINDOW
            )
        if not allowed:
            raise HTTPException(status_code=429, detail="rate_limited")

        try:
            tariff = resolve_tariff(body.plan)
        except (KeyError, ValueError):
            raise HTTPException(status_code=404, detail="unknown_plan")
        if tariff.tier != "standard" or tariff.code == "trial":
            # Card checkout on the site mirrors the bot: standard plans only.
            raise HTTPException(status_code=400, detail="plan_not_purchasable")

        if not yookassa.is_configured():
            raise HTTPException(status_code=503, detail="payments_unavailable")

        try:
            intent = await billing_api.build_web_payment_intent(
                session,
                plan=tariff.code,
                telegram_id=body.telegram_id,
                email=email,
                subscription_link=link,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Покупка с сайта — единственное место, где виден канал для тех, кто
        # никогда не открывал бота, а это большая часть выручки.
        await _tag_source(session, intent.user_id, body.source)

        web_base = get_settings().WEB_BASE_URL.strip().rstrip("/")
        try:
            payment = await yookassa.create_payment(
                amount_kopecks=intent.plan.price_rub * 100,
                description=intent.description,
                metadata={"user_id": intent.user_id, "plan": intent.plan.code, "source": "web"},
                return_url=f"{web_base}/pay/success" if web_base else None,
                receipt_email=email,
            )
        except yookassa.YooKassaError as exc:
            logging.getLogger("yookassa").exception("Web checkout: create payment failed")
            raise HTTPException(status_code=502, detail="payment_create_failed") from exc

        payment_id = payment.get("id")
        pay_url = yookassa.confirmation_url(payment)
        if not payment_id or not pay_url:
            raise HTTPException(status_code=502, detail="payment_create_failed")

        await billing_api.register_yookassa_payment(
            session, intent=intent, external_payment_id=str(payment_id)
        )
        return {
            "orderId": str(payment_id),
            "payUrl": pay_url,
            "plan": _plan_payload(intent.plan),
        }

    @application.get("/web/order/{order_id}")
    async def web_order(order_id: str, session: SessionDep) -> dict[str, Any]:
        repo = Repository(session)
        payment = await repo.get_payment_by_external_id(order_id)
        if payment is None or payment.provider != "yookassa":
            raise HTTPException(status_code=404, detail="order_not_found")
        if payment.status != "completed":
            return {"status": "pending"}

        snapshot = await billing_api.get_subscription_snapshot(session, payment.user_id)
        return {
            "status": "succeeded",
            "subscription": {
                "subscriptionUrl": to_gateway_subscription_url(snapshot.subscription_url),
                "planTitle": snapshot.plan_title,
                "expiresAt": _iso(snapshot.expires_at),
                "isActive": snapshot.is_active,
            },
        }

    @application.post("/web/trial/activate")
    async def web_trial_activate(body: WebTrialRequest, session: SessionDep) -> dict[str, Any]:
        """Site-side trial: same guards as the bot button (no active sub, one
        trial per user), same provisioning path, link returned for display."""
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(body.telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        if await repo.list_active_subscriptions(user.id):
            raise HTTPException(status_code=409, detail="has_active_subscription")
        if await repo.has_used_trial(user.id):
            raise HTTPException(status_code=409, detail="trial_already_used")
        try:
            subscription = await activate_panel_subscription(session=session, user_id=user.id, plan="trial")
        except Exception as exc:  # noqa: BLE001 - surfaced as 502 for the web layer
            log.exception("Web trial activation failed for user_id=%s", user.id)
            raise HTTPException(status_code=502, detail="provisioning_failed") from exc
        return {
            "ok": True,
            "subscriptionUrl": to_gateway_subscription_url(subscription.subscription_url),
        }

    @application.post("/web/track/click")
    async def web_track_click(body: LinkClickRequest, session: SessionDep) -> dict[str, Any]:
        """Count a tap on a /go/<campaign> tracking link.

        Called server-side by the site's redirect route, so the caller is
        already token-authed. Never fails the redirect: an unusable campaign
        name is simply not counted rather than erroring, because losing a
        counter row must never cost a real visitor their click-through.
        """
        campaign = normalize_source_slug(body.campaign)
        if campaign is None:
            return {"ok": False, "counted": False}
        target = "site" if body.target == "site" else "bot"
        await Repository(session).record_link_click(campaign, target=target)
        return {"ok": True, "counted": True, "campaign": campaign}

    # --- «Мой налог» receipts -------------------------------------------------
    # lknpd.nalog.ru answers only to Russian IPs, so the income registration
    # runs off-box (scripts/receipts_job.py on an RU machine). These two routes
    # are its API: list paid orders still lacking a чек, then store the issued
    # чек URL and deliver it to the buyer (Telegram DM / email) from here.

    @application.get("/web/receipts/pending")
    async def web_receipts_pending(session: SessionDep) -> dict[str, Any]:
        repo = Repository(session)
        payments = await repo.list_unreceipted_completed_payments(provider="yookassa")
        items = []
        for payment in payments:
            # HARD GATE against phantom receipts: never hand a payment to the
            # fiscal service on our DB status alone. Re-confirm with YooKassa
            # that it genuinely succeeded for the expected amount — otherwise a
            # payment wrongly marked completed (test, replayed webhook, manual
            # edit) would become real registered income at the tax service.
            if not payment.external_invoice_id:
                continue
            if not await yookassa.verify_paid(payment.external_invoice_id, payment.amount):
                logging.getLogger("receipts").warning(
                    "Skipping receipt for payment %s — not verified paid at YooKassa",
                    payment.id,
                )
                continue
            service_name = settings.MOYNALOG_SERVICE_NAME
            try:
                details = parse_invoice_payload_details(payment.invoice_payload or "")
                service_name = f"UnLockVPN — {billing_api.get_billing_plan(details.plan).title}"
            except ValueError:
                pass
            items.append(
                {
                    "paymentId": payment.id,
                    "amountKopecks": payment.amount,
                    "serviceName": service_name,
                    "createdAt": _iso(payment.created_at),
                }
            )
        return {"items": items}

    @application.post("/web/receipts/{payment_id}/complete")
    async def web_receipts_complete(
        payment_id: int, body: ReceiptCompleteRequest, session: SessionDep
    ) -> dict[str, Any]:
        url = body.receipt_url.strip()
        if not url.startswith("https://lknpd.nalog.ru/"):
            raise HTTPException(status_code=400, detail="invalid_receipt_url")

        repo = Repository(session)
        payment = await repo.get_payment(payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="payment_not_found")
        if payment.receipt_url:
            return {"ok": True, "already": True}

        await repo.set_payment_receipt(payment_id, url)

        delivered_tg = delivered_email = False
        user = await repo.get_user(payment.user_id)
        if user is not None:
            if int(user.telegram_id) > 0:
                delivered_tg = await moynalog.deliver_receipt(int(user.telegram_id), url)
            if (user.email or "").strip():
                delivered_email = await moynalog.deliver_receipt_email(user.email.strip(), url)
        return {"ok": True, "deliveredTelegram": delivered_tg, "deliveredEmail": delivered_email}

    @application.get("/admin/stats")
    async def admin_stats(session: SessionDep) -> dict[str, Any]:
        repo = Repository(session)
        now = datetime.now(timezone.utc)
        active_by_tier = await repo.count_active_subscriptions_by_tier()
        recent_rows = await repo.recent_subscriptions(limit=25)
        recent = []
        for row in recent_rows:
            try:
                plan_title = resolve_tariff(row["plan"]).title
            except ValueError:
                plan_title = row["plan"]
            recent.append(
                {
                    "id": row["id"],
                    "tier": row["tier"],
                    "plan": row["plan"],
                    "planTitle": plan_title,
                    "telegramId": row["telegramId"],
                    "username": row["username"],
                    "isActive": row["isActive"],
                    "startedAt": _iso(row["startedAt"]),
                    "expiresAt": _iso(row["expiresAt"]),
                }
            )
        return {
            "users": {
                "total": await repo.count_users(),
                "new24h": await repo.count_users_since(now - timedelta(days=1)),
                "new7d": await repo.count_users_since(now - timedelta(days=7)),
            },
            "subscriptions": {
                "activeByTier": active_by_tier,
                "activeTotal": sum(active_by_tier.values()),
                "total": await repo.count_subscriptions_total(),
            },
            "recent": recent,
            "generatedAt": _iso(now),
        }

    @application.post("/tribute/webhook")
    async def tribute_webhook(request: Request, session: SessionDep) -> dict[str, Any]:
        raw = await request.body()
        if not tribute.verify_signature(raw, request.headers.get("trbt-signature", "")):
            raise HTTPException(status_code=401, detail="invalid signature")
        try:
            data = json.loads(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid json")

        name = data.get("name")
        payload = data.get("payload") or {}

        # Idempotency: Tribute may retry. Dedupe on the purchase/transaction id.
        event_id = str(
            payload.get("purchase_id")
            or payload.get("transaction_id")
            or f"{name}:{payload.get('subscription_id')}:{payload.get('period_id')}"
        )
        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            fresh = await redis.set(f"tribute:evt:{event_id}", "1", nx=True, ex=60 * 60 * 24 * 7)
            if not fresh:
                return {"ok": True, "deduped": True}

        if name not in ("new_subscription", "new_digital_product"):
            return {"ok": True, "ignored": name}

        telegram_id = payload.get("telegram_user_id")
        tribute_id = payload.get("product_id") if name == "new_digital_product" else payload.get("subscription_id")
        plan = tribute.plan_for(tribute_id)
        if not telegram_id or not plan:
            # Log raw payload so an unmapped product can be wired up afterwards.
            import logging

            logging.getLogger("tribute").error("Unmapped Tribute purchase: %s", raw.decode("utf-8", "replace"))
            return {"ok": False, "error": "unmapped"}

        username = (payload.get("telegram_username") or "").lstrip("@") or None
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=int(telegram_id), username=username)
        try:
            subscription = await activate_panel_subscription(session=session, user_id=user.id, plan=plan)
        except Exception as exc:  # noqa: BLE001 - surface as 500 so Tribute retries
            raise HTTPException(status_code=500, detail="provisioning failed") from exc

        await repo.record_funnel_event(user.id, "payment", meta={"provider": "tribute"})
        sub_url = to_gateway_subscription_url(subscription.subscription_url) or ""
        await tribute.deliver_subscription(int(telegram_id), sub_url)
        return {"ok": True, "plan": plan}

    @application.post("/yookassa/webhook")
    async def yookassa_webhook(request: Request, session: SessionDep) -> dict[str, Any]:
        log = logging.getLogger("yookassa")
        try:
            data = json.loads(await request.body())
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid json")

        obj = data.get("object") if isinstance(data, dict) else None
        payment_id = (obj or {}).get("id")
        if not payment_id:
            raise HTTPException(status_code=400, detail="no payment id")

        # YooKassa does not sign webhooks: treat the body as a hint and re-fetch
        # the payment from the API (authenticated with our secret) as the source
        # of truth before delivering anything.
        try:
            payment = await yookassa.get_payment(str(payment_id))
        except yookassa.YooKassaError as exc:
            log.exception("Failed to verify YooKassa payment %s", payment_id)
            # 5xx so YooKassa retries the webhook later.
            raise HTTPException(status_code=502, detail="verify failed") from exc

        if payment.get("status") != "succeeded":
            return {"ok": True, "ignored": payment.get("status")}

        # Idempotency: YooKassa retries. Dedupe on the payment id.
        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            fresh = await redis.set(f"yookassa:evt:{payment_id}", "1", nx=True, ex=60 * 60 * 24 * 7)
            if not fresh:
                return {"ok": True, "deduped": True}

        repo = Repository(session)
        completed = await repo.complete_payment_by_external_id(str(payment_id), provider="yookassa")
        if completed is None:
            # Unknown id or already completed (a lost dedupe) — nothing to deliver.
            return {"ok": True, "already": True}

        try:
            details = parse_invoice_payload_details(completed.invoice_payload or "")
        except ValueError:
            log.error("Bad YooKassa payload for payment %s: %r", payment_id, completed.invoice_payload)
            return {"ok": False, "error": "bad_payload"}

        # Defense-in-depth: confirm the amount actually paid matches the plan we
        # are about to grant. The intent fixes the amount at creation, so this
        # only trips on tampering or a plan/price desync — never grant on it.
        try:
            paid_kopecks = int(round(float(payment["amount"]["value"]) * 100))
        except (KeyError, TypeError, ValueError):
            paid_kopecks = None
        expected_kopecks = billing_api.get_billing_plan(details.plan).price_rub * 100
        if paid_kopecks is not None and paid_kopecks < expected_kopecks:
            log.error(
                "YooKassa amount mismatch payment=%s paid=%s expected=%s plan=%s",
                payment_id,
                paid_kopecks,
                expected_kopecks,
                details.plan,
            )
            return {"ok": False, "error": "amount_mismatch"}

        if details.user_id != completed.user_id:
            log.error(
                "YooKassa payment user mismatch payment=%s payload_user=%s payment_user=%s",
                payment_id,
                details.user_id,
                completed.user_id,
            )
            return {"ok": False, "error": "user_mismatch"}

        user = await repo.get_user(completed.user_id)
        if user is None:
            return {"ok": False, "error": "no_user"}

        try:
            subscription = await activate_panel_subscription(
                session=session, user_id=completed.user_id, plan=details.plan
            )
        except Exception as exc:  # noqa: BLE001 - surface as 500 so YooKassa retries
            raise HTTPException(status_code=500, detail="provisioning failed") from exc

        # Web email-only buyers have a synthetic negative telegram_id — there is
        # no Telegram chat to DM; they get the link on the site's success page.
        if int(user.telegram_id) > 0:
            sub_url = to_gateway_subscription_url(subscription.subscription_url) or ""
            await tribute.deliver_subscription(int(user.telegram_id), sub_url)

        # Auto-issue the self-employed чек in «Мой налог» and hand its link to the
        # buyer (best-effort; YooKassa no longer forms НПД чеки, so we register the
        # income ourselves). Telegram buyers get a DM; anyone with a saved email
        # also gets the чек by mail — email-only buyers (negative id) have no chat.
        if moynalog.is_configured():
            plan_title = billing_api.get_billing_plan(details.plan).title
            receipt = await moynalog.issue_receipt(completed.amount, name=f"UnLockVPN — {plan_title}")
            if receipt:
                # Record the чек so the off-box receipts job never re-registers
                # this income with ФНС.
                await repo.set_payment_receipt(completed.id, receipt)
                if int(user.telegram_id) > 0:
                    await moynalog.deliver_receipt(int(user.telegram_id), receipt)
                if (user.email or "").strip():
                    await moynalog.deliver_receipt_email(user.email.strip(), receipt)

        return {"ok": True, "plan": details.plan}

    return application


app = create_app()
