"""«Мой налог» (lknpd.nalog.ru) integration — auto-issue self-employed receipts.

YooKassa shut down its «Чеки для самозанятых» service on 2025-12-29, so a
самозанятый must now register each income himself in «Мой налог». This client
uses the ЛКФЛ (inn + password) auth of the unofficial lknpd.nalog.ru API to
register the income after a paid order and returns the public чек URL, which the
bot forwards to the buyer in Telegram.

Best-effort by design: receipt failures are logged and never block delivery.
The access token is short-lived; we cache it in-process and re-auth on expiry.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import aiohttp

from config import settings

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))
_token: str | None = None
_token_expires_at: float = 0.0
_refresh_token: str | None = None  # in-process, seeded from settings, may rotate
_auth_lock = asyncio.Lock()


class MoyNalogError(RuntimeError):
    pass


# ФНС's host is not resolvable through every public resolver: Cloudflare returns
# no answer for it at all, while Yandex and Google return two. That is not a
# curiosity — this job runs on a laptop that is often behind a VPN, and a VPN
# that hands the machine 1.1.1.1 silently takes the tax service off the map.
# Measured 2026-08-03, when three runs in a row failed with a DNS error while
# the machine sat on a foreign tunnel using Cloudflare.
#
# So the host is resolved here, against a resolver known to answer for it,
# instead of depending on whatever the machine currently has. The system
# resolver stays as the fallback.
_RU_RESOLVER = "77.88.8.8"
_RESOLVER_TIMEOUT = 5.0


def _query_a_record(name: str, server: str, timeout: float) -> list[str]:
    """Minimal A-record lookup — stdlib only, no new dependency for one host."""
    import random
    import socket
    import struct

    query = struct.pack(">HHHHHH", random.randint(0, 0xFFFF), 0x0100, 1, 0, 0, 0)
    for label in name.rstrip(".").split("."):
        query += bytes([len(label)]) + label.encode("ascii")
    query += b"\x00" + struct.pack(">HH", 1, 1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(query, (server, 53))
        data, _ = sock.recvfrom(2048)
    finally:
        sock.close()

    answer_count = struct.unpack(">H", data[6:8])[0]
    offset = 12
    while data[offset] != 0:  # skip the echoed question
        offset += data[offset] + 1
    offset += 5
    addresses: list[str] = []
    for _ in range(answer_count):
        if data[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            while data[offset] != 0:
                offset += data[offset] + 1
            offset += 1
        rtype, _, _, length = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        if rtype == 1 and length == 4:
            addresses.append(".".join(str(b) for b in data[offset:offset + 4]))
        offset += length
    return addresses


class _RussianResolver(aiohttp.abc.AbstractResolver):
    """Resolves through a Russian nameserver, falling back to the system one."""

    async def resolve(self, host: str, port: int = 0, family: int = 0) -> list[dict]:
        import socket

        loop = asyncio.get_running_loop()
        try:
            addresses = await loop.run_in_executor(
                None, _query_a_record, host, _RU_RESOLVER, _RESOLVER_TIMEOUT
            )
        except Exception as exc:
            logger.warning("russian resolver failed for %s: %s", host, exc)
            addresses = []
        if addresses:
            return [
                {
                    "hostname": host,
                    "host": address,
                    "port": port,
                    "family": socket.AF_INET,
                    "proto": 0,
                    "flags": socket.AI_NUMERICHOST,
                }
                for address in addresses
            ]
        infos = await loop.getaddrinfo(host, port, family=socket.AF_INET,
                                       type=socket.SOCK_STREAM)
        return [
            {"hostname": host, "host": sockaddr[0], "port": sockaddr[1],
             "family": fam, "proto": proto, "flags": socket.AI_NUMERICHOST}
            for fam, _, proto, _, sockaddr in infos
        ]

    async def close(self) -> None:
        return None


def make_session(timeout_seconds: float = 30.0) -> aiohttp.ClientSession:
    """Session that can reach ФНС regardless of the machine's own resolver."""
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        connector=aiohttp.TCPConnector(resolver=_RussianResolver()),
    )


def is_configured() -> bool:
    if not settings.MOYNALOG_INN.strip():
        return False
    return bool(settings.moynalog_refresh_token.strip() or settings.moynalog_password.strip())


def _device_id() -> str:
    # Must match the id the refresh token was bound to; otherwise derive per INN.
    configured = settings.MOYNALOG_DEVICE_ID.strip()
    if configured:
        return configured
    return hashlib.sha256(f"unlock-{settings.MOYNALOG_INN.strip()}".encode()).hexdigest()[:21]


def _device_info() -> dict[str, Any]:
    return {
        "sourceDeviceId": _device_id(),
        "sourceType": "WEB",
        "appVersion": "1.0.0",
        "metaDetails": {"userAgent": "Mozilla/5.0 (UnLock VPN receipts)"},
    }


def _rub(amount_kopecks: int) -> float:
    return float(Decimal(amount_kopecks) / Decimal(100))


def _now_msk() -> str:
    return datetime.now(_MSK).isoformat(timespec="seconds")


async def _request(
    session: aiohttp.ClientSession, method: str, path: str, *, token: str | None, json: dict[str, Any]
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{settings.MOYNALOG_API_URL.rstrip('/')}{path}"
    proxy = settings.MOYNALOG_PROXY.strip() or None
    async with session.post(url, headers=headers, json=json, proxy=proxy) as response:
        text = await response.text()
        if response.status == 401:
            raise MoyNalogError("unauthorized")
        if response.status >= 400:
            raise MoyNalogError(f"HTTP {response.status}: {text[:300]}")
        try:
            return await response.json()
        except aiohttp.ContentTypeError as exc:
            raise MoyNalogError(f"non-JSON response: {text[:300]}") from exc


async def _authenticate(session: aiohttp.ClientSession) -> None:
    global _token, _token_expires_at, _refresh_token

    seed_refresh = _refresh_token or settings.moynalog_refresh_token.strip()
    if seed_refresh:
        # Preferred: refresh-token grant (no password / SMS needed).
        data = await _request(
            session, "POST", "/auth/token", token=None,
            json={"deviceInfo": _device_info(), "refreshToken": seed_refresh},
        )
    else:
        # Fallback: ЛКФЛ inn + password.
        data = await _request(
            session, "POST", "/auth/lkfl", token=None,
            json={
                "username": settings.MOYNALOG_INN.strip(),
                "password": settings.moynalog_password.strip(),
                "deviceInfo": _device_info(),
            },
        )

    token = data.get("token")
    if not token:
        raise MoyNalogError(f"auth response has no token: {list(data.keys())}")
    _token = str(token)
    # lknpd may rotate the refresh token; keep the freshest one in-process.
    if data.get("refreshToken"):
        _refresh_token = str(data["refreshToken"])
    # Access token is short-lived; refresh a bit early.
    _token_expires_at = time.time() + 240


async def _ensure_token(session: aiohttp.ClientSession) -> str:
    global _token
    async with _auth_lock:
        if _token is None or time.time() >= _token_expires_at:
            await _authenticate(session)
        assert _token is not None
        return _token


def receipt_url(receipt_uuid: str) -> str:
    inn = settings.MOYNALOG_INN.strip()
    return f"{settings.MOYNALOG_API_URL.rstrip('/')}/receipt/{inn}/{receipt_uuid}/print"


async def create_income(amount_kopecks: int, name: str | None = None) -> str:
    """Register income and return the public чек URL. Raises on failure."""
    service_name = (name or settings.MOYNALOG_SERVICE_NAME).strip()[:256]
    amount = _rub(amount_kopecks)
    body = {
        "operationTime": _now_msk(),
        "requestTime": _now_msk(),
        "services": [{"name": service_name, "amount": amount, "quantity": 1}],
        "totalAmount": str(amount),
        "client": {"contactPhone": None, "displayName": None, "incomeType": "FROM_INDIVIDUAL", "inn": None},
        "paymentType": "CASH",
        "ignoreMaxTotalIncomeRestriction": False,
    }
    async with make_session(20) as session:
        token = await _ensure_token(session)
        try:
            data = await _request(session, "POST", "/income", token=token, json=body)
        except MoyNalogError as exc:
            if "unauthorized" not in str(exc):
                raise
            # token expired mid-flight — re-auth once and retry.
            token = await _ensure_token(session)
            data = await _request(session, "POST", "/income", token=token, json=body)

    receipt_uuid = data.get("approvedReceiptUuid")
    if not receipt_uuid:
        raise MoyNalogError(f"income response has no approvedReceiptUuid: {list(data.keys())}")
    return receipt_url(str(receipt_uuid))


async def issue_receipt(amount_kopecks: int, name: str | None = None) -> str | None:
    """Best-effort wrapper: returns the чек URL or None (logged) on any failure."""
    if not is_configured():
        return None
    try:
        return await create_income(amount_kopecks, name=name)
    except Exception:  # noqa: BLE001 - receipts must never break delivery
        logger.exception("Failed to issue «Мой налог» receipt for amount=%s", amount_kopecks)
        return None


async def deliver_receipt_email(email: str, url: str) -> bool:
    """Email the чек link to the buyer (best-effort, needs SMTP configured)."""
    import html

    from services import mailer

    if not url or not email:
        return False
    safe_url = html.escape(url, quote=True)
    text = (
        "Чек по вашей оплате UnLock VPN\n\n"
        f"Открыть чек: {url}\n\n"
        "Чек сформирован в сервисе ФНС «Мой налог».\n"
        "Это письмо отправлено автоматически, отвечать на него не нужно."
    )
    html_body = (
        "<p><b>Чек по вашей оплате UnLock VPN</b></p>"
        f'<p><a href="{safe_url}">Открыть чек</a></p>'
        "<p style=\"color:#888;font-size:13px\">Чек сформирован в сервисе ФНС «Мой налог». "
        "Это письмо отправлено автоматически, отвечать на него не нужно.</p>"
    )
    return await mailer.send_email(email, "Чек по оплате UnLock VPN", text, html=html_body)


async def deliver_receipt(telegram_id: int, url: str) -> bool:
    """DM the чек link to the buyer via the main bot (best-effort)."""
    import html

    token = settings.bot_token
    if not token or not url:
        return False
    text = (
        "🧾 <b>Чек по вашей оплате</b>\n\n"
        f"<a href=\"{html.escape(url, quote=True)}\">Открыть чек</a>\n\n"
        "Чек сформирован в сервисе ФНС «Мой налог»."
    )
    payload = {"chat_id": telegram_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"https://api.telegram.org/bot{token}/sendMessage", json=payload
            ) as resp:
                return resp.status == 200
    except Exception:  # noqa: BLE001
        logger.exception("Failed to deliver receipt link to %s", telegram_id)
        return False
