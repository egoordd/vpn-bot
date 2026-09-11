"""Platega card and SBP payments for the mirror bot.

The mirror is what Platega's bank reviewed, and it runs as its own process with
none of the main bot's payment handlers. Everything a Platega payment needs lives
here: opening the invoice, asking Platega how it went, and turning a confirmed
payment into subscription time exactly once.

Confirmation is pulled, not pushed. The mirror asks Platega about its own open
invoices every few seconds, and again whenever the buyer taps «Проверить
оплату», so no public webhook endpoint is needed and nothing outside the mirror
changes.

A payment moves pending → confirmed → processing → completed. «confirmed» means
the money is in but the subscription is not granted yet; it is what a panel
outage leaves behind, and the next check grants it. Each step is a guarded
UPDATE, so the watcher and a buyer's tap can race without granting time twice.

API: https://docs.platega.io — X-MerchantId and X-Secret on every request.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, Subscription, User
from database.repository import Repository
from services.subscription import activate_panel_subscription
from services.tariffs import resolve_tariff

logger = logging.getLogger(__name__)

PROVIDER = "platega"
BASE_URL = os.environ.get("PLATEGA_BASE_URL", "https://app.platega.io").rstrip("/")
MERCHANT_ID = os.environ.get("PLATEGA_MERCHANT_ID", "").strip()
SECRET = os.environ.get("PLATEGA_SECRET", "").strip()
# Where Platega sends the buyer after the payment page: back to the bot.
RETURN_URL = os.environ.get("PLATEGA_RETURN_URL", "https://t.me/UnLockFreedom_bot").strip()

# Platega's method codes. Only the ones switched on for this merchant are offered.
METHOD_LABELS: dict[int, str] = {
    2: "⚡️ СБП",
    11: "💳 Банковская карта",
    13: "🪙 Криптовалюта",
}
METHOD_NAMES: dict[int, str] = {2: "СБП", 11: "банковская карта", 13: "криптовалюта"}
ENABLED_METHODS: tuple[int, ...] = tuple(
    int(code)
    for code in os.environ.get("PLATEGA_METHODS", "2,11").split(",")
    if code.strip().isdigit() and int(code) in METHOD_LABELS
)

PAID_PLANS = ("standard_1m", "standard_3m", "standard_6m", "standard_12m")

# Platega keeps an invoice open for 15 minutes; a day covers slow bank
# confirmations with room to spare, after which the invoice is closed for good.
WATCH_WINDOW = timedelta(hours=24)
_PAYLOAD_PREFIX = "platega"
_TIMEOUT = aiohttp.ClientTimeout(total=15)


def is_configured() -> bool:
    return bool(MERCHANT_ID and SECRET and ENABLED_METHODS)


class PlategaError(RuntimeError):
    """Platega refused or could not be reached. Never carries credentials."""


class PlategaClient:
    def __init__(self, merchant_id: str | None = None, secret: str | None = None):
        self._merchant_id = merchant_id if merchant_id is not None else MERCHANT_ID
        self._secret = secret if secret is not None else SECRET

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict:
        headers = {
            "X-MerchantId": self._merchant_id,
            "X-Secret": self._secret,
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as http:
                async with http.request(method, f"{BASE_URL}{path}", json=body, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        raise PlategaError(f"{method} {path}: HTTP {resp.status}")
        except aiohttp.ClientError as exc:
            raise PlategaError(f"{method} {path}: {type(exc).__name__}") from exc
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise PlategaError(f"{method} {path}: not JSON") from exc
        if not isinstance(data, dict):
            raise PlategaError(f"{method} {path}: unexpected answer")
        return data

    async def create(
        self, *, amount_rub: int, method: int, description: str, payload: str, user_id: int
    ) -> tuple[str, str]:
        data = await self._request(
            "POST",
            "/transaction/process",
            {
                "paymentMethod": method,
                "paymentDetails": {"amount": amount_rub, "currency": "RUB"},
                "description": description,
                "return": RETURN_URL,
                "failedUrl": RETURN_URL,
                "payload": payload,
                "metadata": {"userId": str(user_id)},
            },
        )
        transaction_id, redirect = data.get("transactionId"), data.get("redirect")
        if not transaction_id or not redirect:
            raise PlategaError("create: no transactionId or redirect in the answer")
        return str(transaction_id), str(redirect)

    async def status(self, transaction_id: str) -> tuple[str, float | None]:
        data = await self._request("GET", f"/transaction/{transaction_id}")
        details = data.get("paymentDetails")
        amount = details.get("amount") if isinstance(details, dict) else None
        return str(data.get("status") or "").upper(), (float(amount) if amount is not None else None)


def make_payload(*, user_id: int, plan: str) -> str:
    return f"{_PAYLOAD_PREFIX}:{user_id}:{plan}:{uuid.uuid4().hex}"


def plan_from_payload(payload: str | None) -> str | None:
    parts = (payload or "").split(":")
    if len(parts) != 4 or parts[0] != _PAYLOAD_PREFIX or parts[2] not in PAID_PLANS:
        return None
    return parts[2]


async def start_payment(
    session: AsyncSession, client: PlategaClient, *, user: User, plan: str, method: int
) -> tuple[Payment, str]:
    """Open an invoice: our row first, then Platega, so no paid invoice is unknown to us."""

    if plan not in PAID_PLANS or method not in ENABLED_METHODS:
        raise ValueError("unknown plan or payment method")
    tariff = resolve_tariff(plan)
    payload = make_payload(user_id=user.id, plan=plan)
    payment = Payment(
        user_id=user.id,
        amount=tariff.price_rub * 100,
        currency="RUB",
        provider=PROVIDER,
        invoice_payload=payload,
        status="pending",
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    try:
        transaction_id, redirect = await client.create(
            amount_rub=tariff.price_rub,
            method=method,
            description=f"Подписка UnLock VPN: {tariff.title}",
            payload=payload,
            user_id=user.telegram_id,
        )
    except Exception:
        payment.status = "failed"
        await session.commit()
        raise
    payment.external_invoice_id = transaction_id
    await session.commit()
    return payment, redirect


@dataclass(frozen=True)
class SettleResult:
    state: str  # pending | completed | already | canceled | mismatch | failed | chargeback
    payment: Payment | None = None
    subscription: Subscription | None = None


Activate = Callable[[AsyncSession, int, str], Awaitable[Subscription]]


async def _move(session: AsyncSession, payment_id: int, frm: str, to: str, **values: Any) -> bool:
    """Guarded status change: only the caller that finds `frm` gets to make it."""

    result = await session.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.status == frm)
        .values(status=to, **values)
        .returning(Payment.id)
    )
    moved = result.scalar_one_or_none() is not None
    await session.commit()
    return moved


async def settle(
    session: AsyncSession,
    client: PlategaClient,
    payment_id: int,
    *,
    activate: Activate = activate_panel_subscription,
) -> SettleResult:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.provider != PROVIDER:
        return SettleResult("already")
    await session.refresh(payment)

    if payment.status == "pending":
        if not payment.external_invoice_id:
            return SettleResult("pending", payment)
        status, amount = await client.status(payment.external_invoice_id)
        if status == "PENDING":
            return SettleResult("pending", payment)
        if status == "CANCELED":
            await _move(session, payment.id, "pending", "canceled")
            return SettleResult("canceled", payment)
        if status == "CHARGEBACKED":
            await _move(session, payment.id, "pending", "chargebacked")
            return SettleResult("chargeback", payment)
        if status != "CONFIRMED":
            return SettleResult("pending", payment)
        expected = payment.amount / 100
        if amount is None or abs(amount - expected) > 0.01:
            await _move(session, payment.id, "pending", "amount_mismatch")
            logger.error("Platega payment %s paid %s, expected %s", payment.id, amount, expected)
            return SettleResult("mismatch", payment)
        if not await _move(session, payment.id, "pending", "confirmed"):
            return SettleResult("already", payment)
        await session.refresh(payment)

    if payment.status != "confirmed":
        return SettleResult("already", payment)

    plan = plan_from_payload(payment.invoice_payload)
    if plan is None or not await _move(session, payment.id, "confirmed", "processing"):
        return SettleResult("already", payment)
    try:
        subscription = await activate(session, payment.user_id, plan)
    except Exception:
        logger.exception("Platega payment %s paid but not granted; will retry", payment.id)
        await session.rollback()
        await _move(session, payment.id, "processing", "confirmed")
        return SettleResult("failed", payment)

    await _move(
        session,
        payment.id,
        "processing",
        "completed",
        provider_payment_charge_id=payment.external_invoice_id,
    )
    await Repository(session).record_funnel_event(payment.user_id, "payment", meta={"provider": PROVIDER})
    await session.refresh(payment)
    return SettleResult("completed", payment, subscription)


async def open_payments(session: AsyncSession) -> list[Payment]:
    """Invoices worth asking Platega about: open, ours, and recent enough to matter."""

    since = datetime.now(timezone.utc) - WATCH_WINDOW
    result = await session.execute(
        select(Payment)
        .where(
            Payment.provider == PROVIDER,
            Payment.status.in_(("pending", "confirmed")),
            Payment.created_at >= since,
        )
        .order_by(Payment.created_at)
    )
    return list(result.scalars().all())


async def expire_stale(session: AsyncSession) -> int:
    """Close invoices nobody paid within the watch window."""

    since = datetime.now(timezone.utc) - WATCH_WINDOW
    result = await session.execute(
        update(Payment)
        .where(Payment.provider == PROVIDER, Payment.status == "pending", Payment.created_at < since)
        .values(status="expired")
    )
    await session.commit()
    return result.rowcount or 0


# --- screens ---------------------------------------------------------------


def checkout_text(plan: str) -> str:
    tariff = resolve_tariff(plan)
    return (
        "🧾 <b>Оформление подписки</b>\n\n"
        f"Тариф: {tariff.title}\n"
        f"Срок: {tariff.duration_days} дней\n"
        f"Сумма: {tariff.price_rub} ₽\n\n"
        "Выберите способ оплаты:"
    )


def invoice_text(plan: str, method: int) -> str:
    tariff = resolve_tariff(plan)
    return (
        "🧾 <b>Счёт создан</b>\n\n"
        f"Тариф: {tariff.title}\n"
        f"Сумма: {tariff.price_rub} ₽\n"
        f"Способ оплаты: {METHOD_NAMES.get(method, '—')}\n\n"
        "Нажмите «Оплатить» — откроется страница платёжного сервиса. После оплаты "
        "подписка включится автоматически, обычно в течение минуты.\n\n"
        "Ссылка на оплату действует 15 минут."
    )


def paid_text(subscription: Subscription, expires_label: str) -> str:
    try:
        title = resolve_tariff(subscription.plan).title
    except ValueError:
        title = subscription.plan
    return (
        "✅ <b>Оплата получена</b>\n\n"
        f"Подписка «{title}» активна до {expires_label}.\n"
        "Ниже — ссылка для подключения устройств."
    )


PENDING_ANSWER = "Оплата ещё не поступила. Если вы уже оплатили, подождите минуту и нажмите ещё раз."
CANCELED_ANSWER = "Этот счёт отменён или истёк. Создайте новый в разделе «💳 Тарифы»."
PROBLEM_ANSWER = "С этим платежом нужна проверка. Напишите в поддержку — разберёмся."
