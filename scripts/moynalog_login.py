#!/usr/bin/env python3
"""One-time «Мой налог» (lknpd.nalog.ru) login via SMS to mint a refresh token.

For self-employed who sign in by phone/PIN (no ЛКФЛ password). Two steps:

  1) send the SMS code to your phone:
       python scripts/moynalog_login.py challenge 79001234567

     prints a challengeToken and a deviceId — keep both for step 2.

  2) exchange the SMS code for a long-lived refresh token:
       python scripts/moynalog_login.py verify 79001234567 <code> <challengeToken> <deviceId>

     prints the two lines to add to .env:
       MOYNALOG_DEVICE_ID=...
       MOYNALOG_REFRESH_TOKEN=...

After that the bot authenticates with the refresh token — no password, no more SMS.
"""
from __future__ import annotations

import asyncio
import secrets
import sys
from datetime import datetime, timedelta, timezone

import aiohttp

BASE = "https://lknpd.nalog.ru/api/v1"
_MSK = timezone(timedelta(hours=3))


def _device_info(device_id: str) -> dict:
    return {
        "sourceDeviceId": device_id,
        "sourceType": "WEB",
        "appVersion": "1.0.0",
        "metaDetails": {"userAgent": "Mozilla/5.0 (UnLock VPN receipts)"},
    }


def _now() -> str:
    return datetime.now(_MSK).isoformat(timespec="seconds")


async def _post(path: str, payload: dict) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.post(f"{BASE}{path}", json=payload, headers={"Content-Type": "application/json"}) as r:
            text = await r.text()
            if r.status >= 400:
                raise SystemExit(f"HTTP {r.status}: {text}")
            return await r.json()


async def challenge(phone: str) -> None:
    device_id = secrets.token_hex(10) + secrets.token_hex(1)[0]  # 21 chars
    data = await _post(
        "/auth/challenge",
        {"phone": phone, "requestTime": _now(), "deviceInfo": _device_info(device_id)},
    )
    print("SMS sent. Keep these for step 2:")
    print("  challengeToken:", data.get("challengeToken"))
    print("  deviceId:", device_id)
    print("  expiresIn(s):", data.get("expireIn"))


async def verify(phone: str, code: str, challenge_token: str, device_id: str) -> None:
    data = await _post(
        "/auth/challenge/verify",
        {
            "phone": phone,
            "code": code,
            "challengeToken": challenge_token,
            "deviceInfo": _device_info(device_id),
        },
    )
    refresh = data.get("refreshToken")
    if not refresh:
        raise SystemExit(f"No refreshToken in response: {data}")
    print("# add to .env:")
    print(f"MOYNALOG_DEVICE_ID={device_id}")
    print(f"MOYNALOG_REFRESH_TOKEN={refresh}")


def main() -> None:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "challenge":
        asyncio.run(challenge(args[1]))
    elif len(args) == 5 and args[0] == "verify":
        asyncio.run(verify(args[1], args[2], args[3], args[4]))
    else:
        print(__doc__)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
