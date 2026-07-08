"""YooKassa card-payment integration.

Flow (mirrors Tribute but API-driven):
  1. The bot creates a payment via ``POST /v3/payments`` (Basic auth with
     shopId:secretKey + an ``Idempotence-Key``), passing our user_id/plan in
     ``metadata`` and getting back a ``confirmation.confirmation_url``.
  2. The buyer pays on the YooKassa page and returns to the bot.
  3. YooKassa POSTs a webhook to ``/yookassa/webhook``. Webhooks are NOT signed,
     so we treat the body as a hint and re-fetch the payment via ``get_payment``
     to confirm ``status == "succeeded"`` before delivering anything.

Amounts are handled in RUB. Receipts (54-ФЗ, самозанятый) are attached when
``YOOKASSA_RECEIPT_ENABLED`` is set.
"""
from __future__ import annotations

import base64
import uuid
from decimal import Decimal
from typing import Any

import aiohttp

from config import settings


class YooKassaError(RuntimeError):
    pass


def is_configured() -> bool:
    """Whether YooKassa card payments are available (shop id + secret present)."""
    return bool(settings.YOOKASSA_SHOP_ID.strip() and settings.yookassa_secret_key.strip())


def _auth_header() -> str:
    shop_id = settings.YOOKASSA_SHOP_ID.strip()
    secret = settings.yookassa_secret_key.strip()
    if not shop_id or not secret:
        raise YooKassaError("YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY is not configured")
    raw = f"{shop_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def rub_value(amount_kopecks: int) -> str:
    """YooKassa wants amounts as a decimal string with 2 places, e.g. '149.00'."""
    return str((Decimal(amount_kopecks) / Decimal(100)).quantize(Decimal("0.01")))


async def _request(
    method: str,
    endpoint: str,
    *,
    json: dict[str, Any] | None = None,
    idempotence_key: str | None = None,
) -> dict[str, Any]:
    url = f"{settings.YOOKASSA_API_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"Authorization": _auth_header(), "Content-Type": "application/json"}
    if method.upper() == "POST":
        headers["Idempotence-Key"] = idempotence_key or str(uuid.uuid4())
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method.upper(), url, headers=headers, json=json) as response:
            try:
                data = await response.json()
            except aiohttp.ContentTypeError as exc:
                text = await response.text()
                raise YooKassaError(f"YooKassa non-JSON response: {response.status} {text}") from exc
            if response.status >= 400:
                raise YooKassaError(f"YooKassa HTTP error: {response.status} {data}")

    if not isinstance(data, dict):
        raise YooKassaError(f"Unexpected YooKassa response: {data}")
    return data


def _receipt(amount_kopecks: int, description: str, email: str | None = None) -> dict[str, Any] | None:
    """54-ФЗ receipt for самозанятый (НПД). vat_code=1 = без НДС.

    Two modes:
    - default: we supply the buyer's ``email`` as ``customer`` (they get their чек;
      ``YOOKASSA_RECEIPT_EMAIL`` is only a fallback).
    - ``YOOKASSA_COLLECT_EMAIL_ON_PAGE``: omit ``customer`` so YooKassa asks for the
      email on its own checkout page (needs the matching shop fiscalization setting).
    """
    if not settings.YOOKASSA_RECEIPT_ENABLED:
        return None

    items = [
        {
            "description": description[:128],
            "quantity": "1.00",
            "amount": {"value": rub_value(amount_kopecks), "currency": "RUB"},
            "vat_code": 1,
            "payment_subject": "service",
            "payment_mode": "full_payment",
        }
    ]

    if settings.YOOKASSA_COLLECT_EMAIL_ON_PAGE:
        return {"items": items}

    email = (email or "").strip() or settings.YOOKASSA_RECEIPT_EMAIL.strip()
    if not email:
        return None
    return {"customer": {"email": email}, "items": items}


async def create_payment(
    *,
    amount_kopecks: int,
    description: str,
    metadata: dict[str, Any],
    return_url: str | None = None,
    idempotence_key: str | None = None,
    receipt_email: str | None = None,
) -> dict[str, Any]:
    """Create a redirect payment; returns the YooKassa payment object."""
    payload: dict[str, Any] = {
        "amount": {"value": rub_value(amount_kopecks), "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url or settings.YOOKASSA_RETURN_URL.strip() or "https://t.me",
        },
        "description": description[:128],
        "metadata": metadata,
    }
    receipt = _receipt(amount_kopecks, description, receipt_email)
    if receipt is not None:
        payload["receipt"] = receipt

    result = await _request("POST", "/payments", json=payload, idempotence_key=idempotence_key)
    if "id" not in result:
        raise YooKassaError(f"YooKassa create payment has no id: {result}")
    return result


async def get_payment(payment_id: str) -> dict[str, Any]:
    """Re-fetch a payment to authoritatively confirm its status (webhook check)."""
    return await _request("GET", f"/payments/{payment_id}")


def confirmation_url(payment: dict[str, Any]) -> str | None:
    confirmation = payment.get("confirmation")
    if isinstance(confirmation, dict):
        url = confirmation.get("confirmation_url")
        if isinstance(url, str) and url:
            return url
    return None
