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
from services import alerts, moynalog  # noqa: E402

logger = logging.getLogger("receipts_job")

DEFAULT_API_URL = "https://23.95.3.18.sslip.io"
LEDGER_PATH = Path(__file__).resolve().parent.parent / "tmp" / "receipts_ledger.json"
HEALTH_PATH = Path(__file__).resolve().parent.parent / "tmp" / "receipts_health.json"

# This job is invisible when it works and equally invisible when it does not:
# it only has something to do on a sale, so a dead ФНС token would be found out
# at the next purchase — the one moment a receipt is legally due. So every run
# proves the connection even with nothing to issue, and says so when it cannot.
#
# The machine is a laptop, not a server: it sleeps, changes networks, and sits
# behind our own VPN, from which ФНС is unreachable by design. A single failure
# means nothing. Three runs in a row — three hours — is a real problem.
FAILURES_BEFORE_ALERT = int(os.getenv("RECEIPTS_FAILURES_BEFORE_ALERT", "3"))


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


def load_health(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or HEALTH_PATH).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_health(state: dict, path: Path | None = None) -> None:
    path = path or HEALTH_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(path)


def judge(previous: dict, ok: bool, reason: str = "") -> tuple[str, dict]:
    """(message to send, new state) from this run's outcome.

    Returns an empty message while a failure is still plausibly the laptop —
    asleep, off the network, or on our own VPN, from which ФНС is unreachable.
    Recovery is announced once, so a silent alert is never left hanging.
    """
    streak = 0 if ok else int(previous.get("failures", 0)) + 1
    alerted = bool(previous.get("alerted", False))
    state = {"failures": streak, "alerted": alerted, "last_reason": reason}

    if ok:
        state["alerted"] = False
        if alerted:
            return "✅ Чеки снова оформляются — связь с «Мой налог» восстановилась.", state
        return "", state

    if streak >= FAILURES_BEFORE_ALERT and not alerted:
        state["alerted"] = True
        return (
            "⚠️ <b>Чеки не оформляются</b>\n"
            f"{reason}\n\n"
            f"Не выходит {streak}-й раз подряд. Пока это длится, оплаты остаются "
            "без чека «Мой налог»."
        ), state
    return "", state


async def _egress_address() -> str:
    """The address ФНС would see us from. Best-effort — never raises."""
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.ipify.org") as response:
                return (await response.text()).strip()
    except Exception:  # noqa: BLE001
        return ""


def describe(exc: Exception, egress: str) -> str:
    """Plain wording for the alert, and the one fact that usually explains it.

    The exit country is only a suspect when we never got an answer. An HTTP
    status is proof ФНС heard us, and blaming the address there is worse than
    saying nothing: this hint sent three separate investigations after the VPN
    while the real fault was the login being refused.
    """
    kind = type(exc).__name__
    reached_fns = "HTTP " in str(exc) or "unauthorized" in str(exc)

    if reached_fns and "entity.not.found" in str(exc):
        return (
            "ФНС не узнаёт наш вход в «Мой налог» — учётка, а не сеть: "
            "тот же ответ приходит на заведомо несуществующий ИНН, так что "
            "пароль здесь ни при чём.\n\n"
            "Проверьте в приложении «Мой налог», открывается ли кабинет и "
            "жив ли статус самозанятого. До этого чеки выписываться не будут."
        )
    if reached_fns:
        return f"ФНС ответила отказом: {exc}\n\nСеть в порядке — отвечает, значит доходим."
    if "DNS" in kind or "Resolve" in kind:
        text = "Не удалось определить адрес ФНС."
    elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        text = "ФНС не отвечает."
    else:
        text = f"{kind}: {exc}"
    if egress:
        text += (
            f"\nВнешний адрес сейчас: <code>{egress}</code>. Если он не российский, "
            "ФНС и не ответит — она отклоняет зарубежные адреса. Наш VPN пускает "
            "<code>.ru</code> напрямую и не мешает; чужой — мешает."
        )
    return text


async def _prove_connection() -> None:
    """Authenticate against ФНС even with nothing to issue.

    Cheap, and it turns "we will find out at the next sale" into "we know
    within the hour" — the token is the part that expires silently.
    """
    async with moynalog.make_session() as session:
        await moynalog._ensure_token(session)


async def main() -> int:
    if not moynalog.is_configured():
        logger.error("MOYNALOG_* is not configured in .env — nothing to do.")
        return 2
    timeout = aiohttp.ClientTimeout(total=30)
    failure = ""
    done = 0
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            done = await run(session)
        if done == 0:
            await _prove_connection()
    except Exception as exc:
        failure = describe(exc, await _egress_address())
        logger.error("run failed: %s (%s)", type(exc).__name__, exc)

    message, state = judge(load_health(), ok=not failure, reason=failure)
    save_health(state)
    if message:
        await alerts.send_alert(message)

    if failure:
        return 1
    logger.info("Done: %s receipt(s) issued.", done)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(asyncio.run(main()))
