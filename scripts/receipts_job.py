"""Register «Мой налог» чеки for paid orders — must run from a Russian IP.

lknpd.nalog.ru (ФНС) geo-blocks foreign addresses, so this job runs on the
owner's Mac (launchd agent, see deploy/mac/) instead of the US bot VPS:

1. pull paid-but-unreceipted orders from the billing API (bearer auth);
2. register each income with ФНС locally via services.moynalog;
3. POST the чек URL back — the VPS stores it on the payment and delivers
   it to the buyer (Telegram DM and/or email).

A local ledger (tmp/receipts_ledger.json) records every income the moment
ФНС confirms it, BEFORE the POST back. If the POST fails, the next run
replays the stored URL instead of registering a duplicate income.

Needs in .env: MOYNALOG_INN + MOYNALOG_PASSWORD (or refresh token),
BILLING_API_TOKEN; optional BILLING_API_URL (defaults to the bot VPS).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from services import moynalog  # noqa: E402

logger = logging.getLogger("receipts_job")

DEFAULT_API_URL = "https://23.95.3.18.sslip.io"
LEDGER_PATH = Path(__file__).resolve().parent.parent / "tmp" / "receipts_ledger.json"


def _api_base() -> str:
    return (os.getenv("BILLING_API_URL") or DEFAULT_API_URL).rstrip("/")


def _auth_headers() -> dict[str, str]:
    token = settings.BILLING_API_TOKEN.get_secret_value().strip()
    if not token:
        raise RuntimeError("BILLING_API_TOKEN is not set")
    return {"Authorization": f"Bearer {token}"}


def load_ledger(path: Path | None = None) -> dict[str, str]:
    """payment_id (str) -> чек URL already registered with ФНС."""
    try:
        data = json.loads((path or LEDGER_PATH).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_ledger(ledger: dict[str, str], path: Path | None = None) -> None:
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False))
    tmp.replace(path)


async def run(session: aiohttp.ClientSession) -> int:
    """Process all pending receipts; returns the number completed."""
    async with session.get(f"{_api_base()}/web/receipts/pending", headers=_auth_headers()) as resp:
        if resp.status != 200:
            raise RuntimeError(f"pending list failed: HTTP {resp.status} {await resp.text()}")
        items = (await resp.json()).get("items", [])

    if not items:
        logger.info("No pending receipts.")
        return 0

    ledger = load_ledger()
    done = 0
    for item in items:
        payment_id = str(item["paymentId"])
        amount = int(item["amountKopecks"])
        name = str(item.get("serviceName") or settings.MOYNALOG_SERVICE_NAME)

        url = ledger.get(payment_id)
        if url:
            logger.info("payment %s: income already registered earlier, replaying чек URL", payment_id)
        else:
            url = await moynalog.create_income(amount, name=name)
            ledger[payment_id] = url
            save_ledger(ledger)  # persist BEFORE the POST so a crash can't duplicate income
            logger.info("payment %s: income %s₽ registered, чек %s", payment_id, amount / 100, url)

        async with session.post(
            f"{_api_base()}/web/receipts/{payment_id}/complete",
            headers=_auth_headers(),
            json={"receiptUrl": url},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"complete failed for payment {payment_id}: HTTP {resp.status} {await resp.text()}"
                )
            body = await resp.json()
        logger.info(
            "payment %s: stored (tg=%s, email=%s)",
            payment_id,
            body.get("deliveredTelegram"),
            body.get("deliveredEmail"),
        )
        done += 1
    return done


async def main() -> int:
    if not moynalog.is_configured():
        logger.error("MOYNALOG_* is not configured in .env — nothing to do.")
        return 2
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        done = await run(session)
    logger.info("Done: %s receipt(s) issued.", done)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(asyncio.run(main()))
