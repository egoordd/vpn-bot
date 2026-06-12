from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal

from services.tariffs import TARIFFS, Tariff, resolve_premium_region, resolve_tariff


PAYMENT_PLAN_CODES = (
    "standard_1m",
    "standard_3m",
    "standard_6m",
    "standard_12m",
    "premium_1m",
    "premium_3m",
    "premium_6m",
    "premium_12m",
)


@dataclass(frozen=True)
class ParsedInvoicePayload:
    user_id: int
    plan: str
    region: str | None = None


def _label_for_days(days: int) -> str:
    if days == 30:
        return "30 дней"
    if days == 90:
        return "90 дней"
    if days == 180:
        return "180 дней"
    if days == 365:
        return "12 месяцев"
    return f"{days} дней"


def _plan_entry(tariff: Tariff) -> dict[str, int | str]:
    return {
        "title": tariff.title,
        "label": _label_for_days(tariff.duration_days),
        "days": tariff.duration_days,
        "rub_amount": tariff.price_rub,
        "crypto_amount": tariff.crypto_amount,
        "description": tariff.description,
    }


PLANS: dict[str, dict[str, int | str]] = {
    code: _plan_entry(TARIFFS[code])
    for code in PAYMENT_PLAN_CODES
}


def normalize_payment_plan_code(plan: str) -> str:
    tariff = resolve_tariff(plan)
    if tariff.code not in PLANS:
        raise ValueError(f"Unknown payment plan: {plan}")
    return tariff.code


def create_invoice_payload(user_id: int, plan: str, region: str | None = None) -> str:
    plan_code = normalize_payment_plan_code(plan)
    tariff = resolve_tariff(plan_code)
    if tariff.tier == "premium":
        if region is None:
            raise ValueError("Premium plan requires region")
        region_code = resolve_premium_region(region).code
        return f"unlock:{user_id}:{plan_code}:{region_code}:{uuid.uuid4().hex}"
    if region is not None:
        raise ValueError("Region is only supported for premium plans")
    return f"unlock:{user_id}:{plan_code}:{uuid.uuid4().hex}"


def parse_invoice_payload_details(payload: str) -> ParsedInvoicePayload:
    parts = payload.split(":")
    if len(parts) not in {4, 5} or parts[0] != "unlock":
        raise ValueError("Invalid invoice payload")

    user_id = int(parts[1])
    raw_plan = parts[2]
    try:
        plan = normalize_payment_plan_code(raw_plan)
    except ValueError:
        raise ValueError("Unknown invoice plan")
    tariff = resolve_tariff(plan)

    region = None
    if len(parts) == 5:
        if tariff.tier != "premium":
            raise ValueError("Region is only supported for premium plans")
        try:
            region = resolve_premium_region(parts[3]).code
        except ValueError:
            raise ValueError("Unknown invoice region")

    return ParsedInvoicePayload(user_id=user_id, plan=plan, region=region)


def parse_invoice_payload(payload: str) -> tuple[int, str]:
    details = parse_invoice_payload_details(payload)
    return details.user_id, details.plan


# ---- Wallet top-up invoices -------------------------------------------------

_TOPUP_PREFIX = "unlock_topup"

# Wallet top-up amounts offered in the bot UI (kopecks).
TOPUP_PRESETS_KOPECKS = (15000, 30000, 60000)

MIN_TOPUP_KOPECKS = 5000
MAX_TOPUP_KOPECKS = 1_000_000


@dataclass(frozen=True)
class ParsedTopupPayload:
    user_id: int
    amount_kopecks: int


def create_topup_payload(user_id: int, amount_kopecks: int) -> str:
    if not MIN_TOPUP_KOPECKS <= amount_kopecks <= MAX_TOPUP_KOPECKS:
        raise ValueError("Top-up amount out of range")
    return f"{_TOPUP_PREFIX}:{user_id}:{amount_kopecks}:{uuid.uuid4().hex}"


def parse_topup_payload(payload: str) -> ParsedTopupPayload | None:
    """Return parsed top-up payload, or ``None`` when payload is not a top-up."""
    parts = payload.split(":")
    if parts[0] != _TOPUP_PREFIX:
        return None
    if len(parts) != 4:
        raise ValueError("Invalid top-up payload")
    try:
        user_id = int(parts[1])
        amount_kopecks = int(parts[2])
    except ValueError as exc:
        raise ValueError("Invalid top-up payload") from exc
    if amount_kopecks <= 0:
        raise ValueError("Invalid top-up amount")
    return ParsedTopupPayload(user_id=user_id, amount_kopecks=amount_kopecks)


def usdt_amount_for_kopecks(amount_kopecks: int, rate_rub_per_usdt: Decimal) -> str:
    """Convert a rouble top-up (kopecks) to a USDT invoice amount string.

    Rounds up to 2 decimals so the credited roubles are always fully covered.
    """
    if rate_rub_per_usdt <= 0:
        raise ValueError("RUB_PER_USDT rate must be positive")
    rub = Decimal(amount_kopecks) / Decimal(100)
    usdt = (rub / rate_rub_per_usdt).quantize(Decimal("0.01"), rounding=ROUND_UP)
    return str(usdt)
