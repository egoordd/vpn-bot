from __future__ import annotations

from typing import Any

import os

import aiohttp

from config import settings


class CryptoBotError(RuntimeError):
    pass


class CryptoBotUnavailableError(CryptoBotError):
    """Transient upstream failure (5xx, HTML error page, network) — not our bug.
    Callers should treat it as "try again later", not log a full traceback."""


def is_configured() -> bool:
    """Whether CryptoBot crypto payments are available (token present)."""
    return bool(settings.CRYPTOBOT_TOKEN.strip())


# How long a crypto invoice stays payable.
#
# It was an hour, which is the wrong scale for this payment method. Paying from
# a CryptoBot balance is instant, but a transfer from an outside wallet has to
# confirm on-chain first, and an hour is not a comfortable margin for that. A
# customer told us on 2026-08-25 that he had paid "within the hour" and found
# nothing credited; his invoice had lapsed unpaid, and no invoice on this
# account has ever been paid — five attempts, none completed.
#
# Six hours costs nothing: an unpaid invoice simply expires later, and the
# payload carries the user and amount, so a late payment still lands correctly.
CRYPTO_INVOICE_TTL = int(os.environ.get("CRYPTO_INVOICE_TTL", str(6 * 3600)))


async def _request(method: str, endpoint: str, **params: Any) -> Any:
    token = settings.CRYPTOBOT_TOKEN.strip()
    if not token:
        raise CryptoBotError("CRYPTOBOT_TOKEN is not configured")

    url = f"{settings.CRYPTOBOT_API_URL.rstrip('/')}/{endpoint}"
    headers = {"Crypto-Pay-API-Token": token}
    clean_params = {key: value for key, value in params.items() if value is not None}
    timeout = aiohttp.ClientTimeout(total=15)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if method.upper() == "GET":
                async with session.get(url, headers=headers, params=clean_params) as response:
                    data = await _read_response(response)
            else:
                async with session.post(url, headers=headers, json=clean_params) as response:
                    data = await _read_response(response)
    except aiohttp.ClientError as exc:  # connection reset, DNS, timeout, …
        raise CryptoBotUnavailableError(f"CryptoBot request failed: {exc}") from exc

    if not data.get("ok"):
        raise CryptoBotError(f"CryptoBot API error: {data.get('error') or data}")
    return data.get("result")


async def _read_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
    # A 5xx/HTML page is CryptoBot having a bad moment, not a client bug — flag
    # it as transient so the poller can retry quietly next tick.
    if response.status >= 500:
        raise CryptoBotUnavailableError(f"CryptoBot upstream {response.status}")
    try:
        data = await response.json()
    except aiohttp.ContentTypeError as exc:
        text = await response.text()
        if response.status >= 400:
            raise CryptoBotUnavailableError(
                f"CryptoBot non-JSON error: {response.status}"
            ) from exc
        raise CryptoBotError(f"CryptoBot returned non-JSON response: {response.status} {text}") from exc

    if response.status >= 400:
        raise CryptoBotError(f"CryptoBot HTTP error: {response.status} {data}")
    return data


async def create_invoice(
    amount: str,
    payload: str,
    description: str,
    asset: str = "USDT",
    expires_in: int = CRYPTO_INVOICE_TTL,
) -> dict[str, Any]:
    result = await _request(
        "POST",
        "createInvoice",
        currency_type="crypto",
        asset=asset,
        amount=amount,
        description=description,
        payload=payload,
        expires_in=expires_in,
        allow_comments=False,
        allow_anonymous=False,
    )
    if not isinstance(result, dict):
        raise CryptoBotError(f"Unexpected createInvoice result: {result}")
    return result


async def get_invoices_by_status(status: str = "paid", count: int = 100) -> list[dict[str, Any]]:
    result = await _request("GET", "getInvoices", status=status, count=count)
    if not isinstance(result, dict):
        raise CryptoBotError(f"Unexpected getInvoices result: {result}")
    items = result.get("items", [])
    return [item for item in items if isinstance(item, dict)]


async def get_invoice_by_id(invoice_id: int) -> dict[str, Any] | None:
    result = await _request("GET", "getInvoices", invoice_ids=str(invoice_id), count=1)
    if not isinstance(result, dict):
        raise CryptoBotError(f"Unexpected getInvoices result: {result}")
    items = result.get("items", [])
    return items[0] if items and isinstance(items[0], dict) else None
