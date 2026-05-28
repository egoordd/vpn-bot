from __future__ import annotations

from typing import Any

import aiohttp

from config import settings


class CryptoBotError(RuntimeError):
    pass


async def _request(method: str, endpoint: str, **params: Any) -> Any:
    token = settings.CRYPTOBOT_TOKEN.strip()
    if not token:
        raise CryptoBotError("CRYPTOBOT_TOKEN is not configured")

    url = f"{settings.CRYPTOBOT_API_URL.rstrip('/')}/{endpoint}"
    headers = {"Crypto-Pay-API-Token": token}
    clean_params = {key: value for key, value in params.items() if value is not None}
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        if method.upper() == "GET":
            async with session.get(url, headers=headers, params=clean_params) as response:
                data = await _read_response(response)
        else:
            async with session.post(url, headers=headers, json=clean_params) as response:
                data = await _read_response(response)

    if not data.get("ok"):
        raise CryptoBotError(f"CryptoBot API error: {data.get('error') or data}")
    return data.get("result")


async def _read_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        data = await response.json()
    except aiohttp.ContentTypeError as exc:
        text = await response.text()
        raise CryptoBotError(f"CryptoBot returned non-JSON response: {response.status} {text}") from exc

    if response.status >= 400:
        raise CryptoBotError(f"CryptoBot HTTP error: {response.status} {data}")
    return data


async def create_invoice(
    amount: str,
    payload: str,
    description: str,
    asset: str = "USDT",
    expires_in: int = 3600,
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
