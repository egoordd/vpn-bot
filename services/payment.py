from __future__ import annotations

import uuid
from dataclasses import dataclass

from services.tariffs import TARIFFS, Tariff, resolve_tariff


PAYMENT_PLAN_CODES = (
    "standard_1m",
    "standard_3m",
    "standard_6m",
    "standard_12m",
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
    if region is not None:
        # Regions existed only to pick a Premium location, and Premium is gone.
        raise ValueError("Region is no longer supported")
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
    resolve_tariff(plan)

    # Five-part payloads carried a Premium region. Premium is gone and nothing
    # mints them any more, but invoices already issued must still be readable:
    # a person who opened one before the change should still be able to pay it.
    # The region itself no longer means anything, so it is dropped rather than
    # resolved against a table that no longer exists.
    return ParsedInvoicePayload(user_id=user_id, plan=plan, region=None)


def parse_invoice_payload(payload: str) -> tuple[int, str]:
    details = parse_invoice_payload_details(payload)
    return details.user_id, details.plan
