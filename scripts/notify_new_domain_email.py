"""Email counterpart of the new-domain notice, for buyers who have no Telegram.

Website purchases create a user with a negative telegram_id and no chat to
message, so the bot broadcast cannot reach them at all. They still hold a
subscription pinned to the old host, and email is the only channel we have.

Standalone on purpose, same as the Telegram script: it runs once and leaves the
bot untouched. Dry-run unless --send is passed.

    python3 scripts/notify_new_domain_email.py buyer@example.com
    python3 scripts/notify_new_domain_email.py buyer@example.com --send
    python3 scripts/notify_new_domain_email.py --all --send
"""

from __future__ import annotations

import argparse
import asyncio
import html as html_escape
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import Subscription, User
from services import mailer
from services.subscription import to_gateway_subscription_url, to_happ_import_url
from services.tariffs import resolve_tariff


SEND_INTERVAL_SECONDS = 2.0

SUBJECT = "UnLock VPN: обновите ссылку подписки"

INTRO_TEXT = (
    "Мы переехали на новый адрес: прежний перестал открываться у части операторов связи.\n\n"
    "Ваш VPN продолжает работать, платить ничего не нужно, тариф и срок не меняются. "
    "Но приложение больше не сможет получать со старого адреса новые локации "
    "и продлённый срок.\n\n"
    "Что сделать: откройте ссылку ниже — подписка добавится в приложение сама. "
    "После этого удалите в приложении старую запись, она обновляться не будет.\n"
)

INTRO_HTML = (
    "<p>Мы переехали на новый адрес: прежний перестал открываться у части операторов связи.</p>"
    "<p>Ваш VPN продолжает работать, платить ничего не нужно, тариф и срок не меняются. "
    "Но приложение больше не сможет получать со старого адреса новые локации "
    "и продлённый срок.</p>"
    "<p><b>Что сделать:</b> откройте ссылку ниже — подписка добавится в приложение сама. "
    "После этого удалите в приложении старую запись, она обновляться не будет.</p>"
)


def _tariff_title(plan: str) -> str:
    try:
        return resolve_tariff(plan).title
    except ValueError:
        return plan


def _links(subscriptions: list[Subscription]) -> list[tuple[str, str, str]]:
    """(caption, one-tap import link, raw subscription link), newest first.

    Deduplicated by link: renewals extend one panel line, so several rows can
    share a token, and repeating the same link would only cause doubt.
    """
    by_url: dict[str, Subscription] = {}
    for subscription in subscriptions:
        gateway = to_gateway_subscription_url(subscription.subscription_url)
        if not gateway:
            continue
        current = by_url.get(gateway)
        if current is None or subscription.expires_at > current.expires_at:
            by_url[gateway] = subscription

    result = []
    for gateway, subscription in sorted(
        by_url.items(), key=lambda item: item[1].expires_at, reverse=True
    ):
        caption = (
            f"{_tariff_title(subscription.plan)} — "
            f"до {subscription.expires_at.strftime('%d.%m.%Y')}"
        )
        result.append((caption, to_happ_import_url(gateway, auto=True) or gateway, gateway))
    return result


def build_body(subscriptions: list[Subscription]) -> tuple[str, str] | None:
    links = _links(subscriptions)
    if not links:
        return None

    text = [INTRO_TEXT]
    html = [INTRO_HTML]
    for caption, import_url, raw_url in links:
        text.append(f"\n{caption}\nДобавить в приложение: {import_url}\nСсылка подписки: {raw_url}\n")
        html.append(
            f"<p><b>{html_escape.escape(caption)}</b><br>"
            f'<a href="{html_escape.escape(import_url)}">Добавить в приложение</a><br>'
            f'<span style="font-size:12px;color:#555">Ссылка подписки: '
            f"{html_escape.escape(raw_url)}</span></p>"
        )
    text.append("\nЕсли что-то не получится — напишите в поддержку, поможем.\n")
    html.append("<p>Если что-то не получится — напишите в поддержку, поможем.</p>")
    return "".join(text), "".join(html)


async def load_targets(session, emails: list[str] | None) -> list[tuple[str, list[Subscription]]]:
    now = datetime.now(timezone.utc)
    query = (
        select(Subscription, User)
        .join(User, User.id == Subscription.user_id)
        .where(Subscription.expires_at > now, User.email.is_not(None))
    )
    if emails:
        lowered = [e.strip().lower() for e in emails]
        query = query.where(User.email.in_(lowered))
    else:
        # Everyone reachable by bot already got the Telegram notice; email is
        # for the website buyers who have no chat with the bot at all.
        query = query.where(User.telegram_id < 0)

    grouped: dict[str, list[Subscription]] = {}
    for subscription, user in (await session.execute(query)).all():
        grouped.setdefault(user.email.strip().lower(), []).append(subscription)
    return sorted(grouped.items())


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("emails", nargs="*", help="кому отправить")
    parser.add_argument("--all", action="store_true", help="всем покупателям с сайта")
    parser.add_argument("--send", action="store_true", help="отправить (иначе только показать)")
    args = parser.parse_args()

    if not args.emails and not args.all:
        parser.error("укажите адрес или --all")
    if args.send and not mailer.is_configured():
        print("Почта не настроена: проверьте SMTP_* в .env")
        return 1

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_pool() as session:
            targets = await load_targets(session, args.emails or None)
    finally:
        await engine.dispose()

    if not targets:
        print("Некому отправлять: активных подписок по этим адресам нет.")
        return 1

    print(f"Адресов: {len(targets)}  |  режим: {'ОТПРАВКА' if args.send else 'предпросмотр'}\n")
    sent = failed = 0
    for index, (email, subscriptions) in enumerate(targets):
        body = build_body(subscriptions)
        if body is None:
            print(f"  {email}: пропуск, не удалось собрать ссылку")
            failed += 1
            continue
        text, html = body

        if not args.send:
            captions = ", ".join(c for c, _, _ in _links(subscriptions))
            print(f"  {email}: {captions}")
            print(f"    первая ссылка: {_links(subscriptions)[0][1]}")
            continue

        ok = await mailer.send_email(email, SUBJECT, text, html)
        print(f"  {email}: {'доставлено' if ok else 'ОШИБКА отправки'}")
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
