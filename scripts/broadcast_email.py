"""Email counterpart of scripts/broadcast.py, for buyers the bot cannot reach.

A website purchase creates a user under a synthetic negative telegram_id and no
chat, so a Telegram broadcast skips them entirely. Email is the only channel
they have, and by default that is exactly who this sends to — the handful who
have both an address and a bot chat would otherwise get the same news twice.

    python3 scripts/broadcast_email.py                     # preview, site buyers
    python3 scripts/broadcast_email.py --audience all      # preview, every address
    python3 scripts/broadcast_email.py buyer@example.com   # preview, one address
    python3 scripts/broadcast_email.py --send

Addresses are deduplicated: one person can hold several subscriptions, and two
identical letters read as a mistake.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import User
from services import mailer


# Slower than the Telegram pace: a burst of near-identical letters from one
# mailbox is what spam filters are built to notice.
SEND_INTERVAL_SECONDS = 2.0

CHANNEL_POST_URL = "https://t.me/UnlockAccess/51"
CHANNEL_URL = "https://t.me/UnlockAccess"
SITE_URL = "https://unlockproject.site"
SUPPORT_URL = "https://t.me/unlock_support_bot"
SUPPORT_EMAIL = "unlockvpnru@gmail.com"

SUBJECT = "UnLock VPN: связали аккаунты сайта и бота"

CABINET_URL = f"{SITE_URL}/cabinet"

TEXT = f"""Внесённые изменения

• В боте появилась команда /link — привязывает подписку, купленную на сайте,
  к вашему аккаунту в Telegram.

• На сайте появился вход по ссылке подписки — вкладка «По ссылке» на странице
  входа в личный кабинет: {CABINET_URL}

Зачем это нужно

Сайт и бот раньше не знали друг о друге. Человек оплачивал на сайте, открывал
бота и видел пустоту. Деньги никуда не пропадали, подписка просто лежала на
второй учётной записи, но со стороны это выглядело как «оплатил и потерял».
Теперь записи объединяются, и подписка видна в обоих местах.

Вход по ссылке закрывает вторую половину той же проблемы. Если покупали без
пароля, попасть в личный кабинет было нечем. Теперь вставляете ссылку подписки,
задаёте пароль и заходите как обычно.

Переподключать ничего не нужно, ссылка в приложении остаётся прежней.

Поддержка

Ответьте на это письмо или напишите в Telegram: {SUPPORT_URL}
Почта: {SUPPORT_EMAIL}
"""

HTML = f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;line-height:1.55;color:#1a1a1a;max-width:560px">
  <p style="font-size:18px;font-weight:600;margin:0 0 16px">Связали аккаунты сайта и бота</p>
  <p style="font-weight:600;margin-bottom:6px">Внесённые изменения</p>
  <ul style="margin:0 0 18px;padding-left:20px">
    <li style="margin-bottom:8px">В боте появилась команда <b>/link</b> — привязывает подписку,
      купленную на сайте, к вашему аккаунту в Telegram.</li>
    <li>На сайте появился вход по ссылке подписки — вкладка «По ссылке» на странице
      <a href="{CABINET_URL}">входа в личный кабинет</a>.</li>
  </ul>
  <p style="font-weight:600;margin-bottom:6px">Зачем это нужно</p>
  <p>Сайт и бот раньше не знали друг о друге. Человек оплачивал на сайте, открывал бота и видел
    пустоту. Деньги никуда не пропадали, подписка просто лежала на второй учётной записи, но со
    стороны это выглядело как «оплатил и потерял». Теперь записи объединяются, и подписка видна
    в обоих местах.</p>
  <p>Вход по ссылке закрывает вторую половину той же проблемы. Если покупали без пароля, попасть
    в личный кабинет было нечем. Теперь вставляете ссылку подписки, задаёте пароль и заходите
    как обычно.</p>
  <p>Переподключать ничего не нужно, ссылка в приложении остаётся прежней.</p>
  <p style="margin:20px 0">
    <a href="{CABINET_URL}" style="background:#2481cc;color:#fff;text-decoration:none;padding:11px 18px;border-radius:6px;display:inline-block">Личный кабинет</a>
  </p>
  <p style="font-weight:600;margin-bottom:6px">Поддержка</p>
  <p style="color:#555;font-size:14px">
    Ответьте на это письмо или напишите в Telegram:
    <a href="{SUPPORT_URL}">@unlock_support_bot</a><br>
    Почта: {html.escape(SUPPORT_EMAIL)}
  </p>
</div>
"""


async def load_addresses(session, audience: str, explicit: list[str] | None) -> list[str]:
    query = select(User.email).where(User.email.is_not(None), User.email != "")
    if explicit:
        query = query.where(User.email.in_([a.strip().lower() for a in explicit]))
    elif audience == "site":
        # Negative ids are website buyers with no chat behind them; everyone else
        # is reachable by the Telegram broadcast and must not get this twice.
        query = query.where(User.telegram_id < 0)
    seen = {(row or "").strip().lower() for row in (await session.execute(query)).scalars()}
    return sorted(
        address for address in seen if address and not _is_undeliverable(address)
    )


# Reserved domains never accept mail (RFC 2606/6761). One audit fixture already
# sits in the table, and a bounce off a burst of real letters is the kind of
# thing a sending mailbox gets judged on.
_UNDELIVERABLE_SUFFIXES = (
    "@example.com",
    "@example.org",
    "@example.net",
    ".invalid",
    ".test",
    ".localhost",
)


def _is_undeliverable(address: str) -> bool:
    return address.endswith(_UNDELIVERABLE_SUFFIXES)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("emails", nargs="*", help="кому отправить поимённо")
    parser.add_argument(
        "--audience",
        choices=("site", "all"),
        default="site",
        help="site — покупатели с сайта, которых нет в боте; all — все адреса",
    )
    parser.add_argument("--send", action="store_true", help="отправить (иначе только показать)")
    args = parser.parse_args()

    if args.send and not mailer.is_configured():
        print("Почта не настроена: проверьте SMTP_* в .env")
        return 1

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_pool() as session:
            addresses = await load_addresses(session, args.audience, args.emails or None)
    finally:
        await engine.dispose()

    if not addresses:
        print("Некому отправлять.")
        return 1

    mode = "ОТПРАВКА" if args.send else "предпросмотр"
    print(f"Адресов: {len(addresses)}  |  аудитория: {args.audience}  |  режим: {mode}\n")

    if not args.send:
        print(f"--- тема ---\n{SUBJECT}\n")
        print(f"--- текст ---\n{TEXT}")
        print("--- получатели ---")
        for address in addresses[:10]:
            print(f"  {address}")
        if len(addresses) > 10:
            print(f"  …и ещё {len(addresses) - 10}")
        print(f"\nОтправка займёт около {round(len(addresses) * SEND_INTERVAL_SECONDS / 60)} мин.")
        print("Это предпросмотр. Добавьте --send, чтобы отправить.")
        return 0

    sent = 0
    failures: list[str] = []
    for index, address in enumerate(addresses):
        ok = await mailer.send_email(address, SUBJECT, TEXT, HTML)
        sent += ok
        if not ok:
            failures.append(address)
        if (index + 1) % 10 == 0:
            print(f"  отправлено {index + 1} из {len(addresses)}…")
        if index + 1 < len(addresses):
            await asyncio.sleep(SEND_INTERVAL_SECONDS)

    print(f"\nИтого: доставлено {sent}, не доставлено {len(failures)}")
    for address in failures:
        print(f"  {address}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
