"""One-off notice that the subscription address moved to a new domain.

Existing installs keep a subscription URL on the old host, which a growing share
of Russian operators no longer resolve. The tunnels themselves keep working
(they dial node IPs directly), so nothing looks broken to the user until their
app quietly stops picking up new locations or a renewed expiry date.

This is deliberately a standalone script rather than a bot feature: it runs
once, needs no handler, and leaves the bot untouched. Ordering is one message
per user, paced under Telegram's limits, dry-run unless --send is passed.

    python3 scripts/notify_new_domain.py 740484324          # preview only
    python3 scripts/notify_new_domain.py 740484324 --send    # actually send
    python3 scripts/notify_new_domain.py --all --send        # every reachable user
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import Subscription, User
from services.subscription import to_gateway_subscription_url, to_happ_import_url
from services.tariffs import resolve_tariff


# Telegram tolerates ~30 messages/second; one every 1.5s keeps a broadcast well
# inside that even when several subscriptions widen a single message.
SEND_INTERVAL_SECONDS = 1.5

MESSAGE = (
    "🔄 <b>Обновите ссылку подписки</b>\n\n"
    "Мы переехали на новый адрес: прежний перестал открываться у части операторов связи.\n\n"
    "Ваш VPN продолжает работать, платить ничего не нужно, тариф и срок не меняются. "
    "Но приложение больше не сможет получать со старого адреса новые локации и продлённый срок.\n\n"
    "<b>Что сделать:</b> нажмите кнопку ниже, подписка добавится в приложение сама. "
    "После этого удалите в приложении старую запись — она останется рядом и обновляться не будет."
)


def _tariff_title(plan: str) -> str:
    try:
        return resolve_tariff(plan).title
    except ValueError:
        return plan


def build_keyboard(subscriptions: list[Subscription]) -> dict | None:
    """One import button per distinct link, newest expiry first.

    Renewals extend a single panel line, so several subscription rows routinely
    share one token — and one button. Four identical buttons would only make the
    user guess which one is theirs.
    """

    by_url: dict[str, Subscription] = {}
    for subscription in subscriptions:
        gateway = to_gateway_subscription_url(subscription.subscription_url)
        happ = to_happ_import_url(gateway, auto=True)
        if not happ:
            continue
        current = by_url.get(happ)
        if current is None or subscription.expires_at > current.expires_at:
            by_url[happ] = subscription

    rows = []
    for happ, subscription in sorted(
        by_url.items(), key=lambda item: item[1].expires_at, reverse=True
    ):
        # Telegram truncates long captions, so the date stays numeric.
        until = subscription.expires_at.strftime("%d.%m.%Y")
        label = f"🔄 {_tariff_title(subscription.plan)} — до {until}"
        rows.append([{"text": label[:64], "url": happ}])
    if not rows:
        return None
    return {"inline_keyboard": rows}


async def load_targets(session, telegram_ids: list[int] | None) -> list[tuple[User, list[Subscription]]]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    query = select(Subscription, User).join(User, User.id == Subscription.user_id).where(
        Subscription.expires_at > now,
        # Negative ids are website buyers who never opened the bot; a DM would
        # fail for them and they need the email path instead.
        User.telegram_id > 0,
    )
    if telegram_ids:
        query = query.where(User.telegram_id.in_(telegram_ids))

    grouped: dict[int, tuple[User, list[Subscription]]] = {}
    for subscription, user in (await session.execute(query)).all():
        entry = grouped.setdefault(user.telegram_id, (user, []))
        entry[1].append(subscription)
    for _, subscriptions in grouped.values():
        subscriptions.sort(key=lambda s: s.expires_at, reverse=True)
    return list(grouped.values())


async def send(api_base: str, chat_id: int, keyboard: dict) -> tuple[bool, str]:
    payload = {
        "chat_id": chat_id,
        "text": MESSAGE,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
        "reply_markup": keyboard,
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{api_base}/sendMessage", json=payload) as response:
            body = await response.json(content_type=None)
    if body.get("ok"):
        return True, "доставлено"
    return False, str(body.get("description") or f"HTTP {response.status}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telegram_ids", nargs="*", type=int, help="кому отправить")
    parser.add_argument("--all", action="store_true", help="всем, у кого есть активная подписка")
    parser.add_argument("--send", action="store_true", help="отправить (иначе только показать)")
    args = parser.parse_args()

    if not args.telegram_ids and not args.all:
        parser.error("укажите telegram_id или --all")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_pool() as session:
            targets = await load_targets(session, args.telegram_ids or None)
    finally:
        await engine.dispose()

    if not targets:
        print("Некому отправлять: активных подписок у указанных получателей нет.")
        return 1

    # BOT_TOKEN is a SecretStr: interpolating it directly yields "**********"
    # and a 404 from Telegram that reads like a missing chat.
    token = settings.BOT_TOKEN
    token = token.get_secret_value() if hasattr(token, "get_secret_value") else str(token)
    api_base = f"https://api.telegram.org/bot{token}"
    print(f"Получателей: {len(targets)}  |  режим: {'ОТПРАВКА' if args.send else 'предпросмотр'}\n")

    sent = failed = 0
    for index, (user, subscriptions) in enumerate(targets):
        keyboard = build_keyboard(subscriptions)
        name = user.username or str(user.telegram_id)
        if keyboard is None:
            print(f"  {name}: пропуск, не удалось собрать ссылку")
            failed += 1
            continue

        labels = ", ".join(b[0]["text"] for b in keyboard["inline_keyboard"])
        if not args.send:
            print(f"  {name} ({user.telegram_id}): {labels}")
            print(f"    первая ссылка: {keyboard['inline_keyboard'][0][0]['url']}")
            continue

        ok, detail = await send(api_base, user.telegram_id, keyboard)
        print(f"  {name} ({user.telegram_id}): {detail}")
        sent += ok
        failed += not ok
        if index + 1 < len(targets):
            await asyncio.sleep(SEND_INTERVAL_SECONDS)

    if args.send:
        print(f"\nИтого: доставлено {sent}, не доставлено {failed}")
    else:
        print("\nЭто предпросмотр. Добавьте --send, чтобы отправить.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
