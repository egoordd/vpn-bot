from __future__ import annotations

import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.repository import Repository
from services import billing_api, moynalog, promo, tribute, wallet, yookassa
from services.billing_api import AccountOverview, BillingPlan, BillingRegion, SubscriptionSnapshot
from services.payment import parse_invoice_payload_details
from services.referral import reward_referrer_for_payment, ReferralStats
from services.subscription import activate_panel_subscription, to_gateway_subscription_url
from services.tariffs import resolve_tariff
from services.wallet import UnknownWalletUserError, WalletEntry, WalletSnapshot

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


class WebCheckoutRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plan: str = Field(min_length=1, max_length=64)
    telegram_id: int | None = Field(default=None, alias="telegramId", gt=0)
    email: str | None = Field(default=None, max_length=320)


class WebEmailUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    telegram_id: int = Field(alias="telegramId", gt=0)
    email: str = Field(min_length=3, max_length=320)


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


def _region_payload(region: BillingRegion) -> dict[str, Any]:
    return {
        "code": region.code,
        "title": region.title,
        "city": region.city,
        "countryCode": region.country_code,
        "isOnDemand": region.is_on_demand,
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


def _wallet_entry_payload(entry: WalletEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "amountKopecks": entry.amount_kopecks,
        "balanceAfterKopecks": entry.balance_after_kopecks,
        "kind": entry.kind,
        "description": entry.description,
        "createdAt": _iso(entry.created_at),
    }


def _wallet_payload(snapshot: WalletSnapshot) -> dict[str, Any]:
    return {
        "balanceKopecks": snapshot.balance_kopecks,
        "entries": [_wallet_entry_payload(entry) for entry in snapshot.entries],
    }


def _referral_payload(stats: ReferralStats) -> dict[str, Any]:
    return {
        "refCode": stats.ref_code,
        "rewardPercent": stats.reward_percent,
        "referralsCount": stats.referrals_count,
        "totalEarnedKopecks": stats.total_earned_kopecks,
    }


def _account_payload(account: AccountOverview) -> dict[str, Any]:
    return {
        "userId": account.user_id,
        "telegramId": account.telegram_id,
        "subscription": _subscription_payload(account.subscription),
        "wallet": _wallet_payload(account.wallet),
        "balanceDisplay": account.balance_display,
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

    @application.get("/regions")
    async def regions() -> dict[str, Any]:
        items = billing_api.list_billing_regions()
        return {"regions": [_region_payload(region) for region in items]}

    @application.get("/account/{user_id}")
    async def account(user_id: int, session: SessionDep) -> dict[str, Any]:
        try:
            overview = await billing_api.get_account_overview(session, user_id)
        except (ValueError, UnknownWalletUserError):
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

    @application.get("/web/account/by-telegram/{telegram_id}")
    async def web_account_by_telegram(telegram_id: int, session: SessionDep) -> dict[str, Any]:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        try:
            overview = await billing_api.get_account_overview(session, user.id)
        except (ValueError, UnknownWalletUserError):
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

    @application.post("/web/checkout")
    async def web_checkout(body: WebCheckoutRequest, session: SessionDep) -> dict[str, Any]:
        from config import get_settings

        email = (body.email or "").strip().lower() or None
        if body.telegram_id is None and email is None:
            raise HTTPException(status_code=400, detail="identity_required")
        if email is not None and not _WEB_EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="invalid_email")

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
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

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
            "money": {
                "balancesKopecks": await repo.sum_all_user_balances(),
                "depositsKopecks": await repo.sum_all_wallet_by_kind(wallet.KIND_DEPOSIT),
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

        try:
            await reward_referrer_for_payment(
                session,
                paid_user_id=completed.user_id,
                plan_code=details.plan,
                payment_reference=f"yookassa:{payment_id}",
            )
        except Exception:
            log.exception("Referral reward failed for YooKassa payment %s", payment_id)

        # Web email-only buyers have a synthetic negative telegram_id — there is
        # no Telegram chat to DM; they get the link on the site's success page.
        if int(user.telegram_id) > 0:
            sub_url = to_gateway_subscription_url(subscription.subscription_url) or ""
            await tribute.deliver_subscription(int(user.telegram_id), sub_url)

        # Auto-issue the self-employed чек in «Мой налог» and DM its link (best-effort;
        # YooKassa no longer forms НПД чеки, so we register the income ourselves).
        if moynalog.is_configured():
            plan_title = billing_api.get_billing_plan(details.plan).title
            receipt = await moynalog.issue_receipt(completed.amount, name=f"Оплата подписки: {plan_title}")
            if receipt and int(user.telegram_id) > 0:
                await moynalog.deliver_receipt(int(user.telegram_id), receipt)

        return {"ok": True, "plan": details.plan}

    return application


app = create_app()
