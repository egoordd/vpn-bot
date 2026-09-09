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
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import User
from services import mailer


# Slower than the Telegram pace: a burst of near-identical letters from one
# mailbox is what spam filters are built to notice.
SEND_INTERVAL_SECONDS = 2.0

# Written the moment a letter goes out, so a run cut short can be resumed
# without sending the same news to the same person twice.
LEDGER = Path("/opt/vpn-bot/var/broadcast_block_email_sent.txt")

CHANNEL_POST_URL = "https://t.me/UnlockAccess/51"
CHANNEL_URL = "https://t.me/UnlockAccess"
SITE_URL = "https://unlockproject.site"
SUPPORT_URL = "https://t.me/unlock_support_bot"
SUPPORT_EMAIL = "unlockvpnru@gmail.com"

SUBJECT = "РКН заблокировал наш сайт — переезжаем на новый адрес"

CABINET_URL = f"{SITE_URL}/cabinet"

TEXT = f"""РКН заблокировал наш сайт. Переезжаем на новый.

Прежний адрес перестал открываться у части операторов связи.
Новый сайт работает здесь: {SITE_URL}

Все ваши данные на месте: подписки, сроки и ссылки сохранились, оформлять
заново ничего не нужно. Личный кабинет теперь здесь: {CABINET_URL}
Если вы покупали без пароля, на странице входа написано, как восстановить доступ.

Подписки пока работают на прежнем адресе — ссылку в приложении менять не нужно,
удалять тоже. Переносить их на новый домен будем постепенно, и когда дойдёт
очередь до вашей, мы напишем вам на эту почту таким же письмом.

Пока идёт переезд, подписка может вести себя неровно: приложение иногда не
обновит список серверов или не сразу подключит новое устройство. Само
подключение при этом работает. Если что-то отвалится — загляните в личный
кабинет или напишите нам, поможем и компенсируем потерянное время.

Такое будет повторяться: адреса блокируют, мы переезжаем на новые. Чтобы не
потерять с нами связь, подпишитесь на наш канал — там мы сразу публикуем новый
адрес, предупреждаем о работах и выкладываем промокоды:
{CHANNEL_URL}

Подробности сегодняшней ситуации: {CHANNEL_POST_URL}

Поддержка: ответьте на это письмо или напишите в Telegram {SUPPORT_URL}
Почта: {SUPPORT_EMAIL}
"""

HTML = f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;line-height:1.55;color:#1a1a1a;max-width:560px">
  <p style="font-size:18px;font-weight:600;margin:0 0 16px">
    <a href="{CHANNEL_POST_URL}" style="color:#1a1a1a">🚫 РКН заблокировал наш сайт. Переезжаем на новый</a>
  </p>
  <p>Прежний адрес перестал открываться у части операторов связи. Новый сайт работает здесь:
    <a href="{SITE_URL}">unlockproject.site</a></p>
  <p><b>Все ваши данные на месте:</b> подписки, сроки и ссылки сохранились, оформлять заново
    ничего не нужно. Личный кабинет теперь <a href="{CABINET_URL}">здесь</a>.<br>
    <span style="color:#555;font-size:14px">Если вы покупали без пароля, на странице входа
    написано, как восстановить доступ.</span></p>
  <p><b>Подписки пока работают на прежнем адресе</b> — ссылку в приложении менять не нужно,
    удалять тоже. Переносить их на новый домен будем постепенно, и когда дойдёт очередь
    до вашей, мы напишем вам на эту почту таким же письмом.</p>
  <p><b>Пока идёт переезд, подписка может вести себя неровно:</b> приложение иногда не обновит
    список серверов или не сразу подключит новое устройство. Само подключение при этом работает.
    Если что-то отвалится — загляните в личный кабинет или напишите нам, поможем и компенсируем
    потерянное время.</p>
  <p><b>Такое будет повторяться.</b> Адреса блокируют, мы переезжаем на новые. Чтобы не потерять
    с нами связь, подпишитесь на наш канал — там мы сразу публикуем новый адрес, предупреждаем
    о работах и выкладываем промокоды.</p>
  <p style="margin:20px 0">
    <a href="{CHANNEL_URL}" style="background:#2481cc;color:#fff;text-decoration:none;padding:11px 18px;border-radius:6px;display:inline-block">📣 Подписаться на канал</a>
    <a href="{CABINET_URL}" style="border:1px solid #ccc;color:#1a1a1a;text-decoration:none;padding:10px 18px;border-radius:6px;display:inline-block;margin-left:8px">Личный кабинет</a>
  </p>
  <p style="color:#555;font-size:14px">
    Поддержка: ответьте на это письмо или напишите
    <a href="{SUPPORT_URL}">@unlock_support_bot</a><br>
    Почта: {html.escape(SUPPORT_EMAIL)}
  </p>
</div>
"""


def already_delivered(ledger: Path) -> set[str]:
    if not ledger.exists():
        return set()
    return {
        line.strip().lower()
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def record(ledger: Path, address: str) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(f"{address}\n")
        fh.flush()


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
    parser.add_argument(
        "--state",
        default=str(LEDGER),
        help="файл с уже отправленными адресами; повтор запуска их пропустит",
    )
    args = parser.parse_args()
    ledger = Path(args.state)

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

    delivered = already_delivered(ledger)
    if delivered:
        before = len(addresses)
        addresses = [a for a in addresses if a not in delivered]
        print(f"Уже получили в прошлый раз: {before - len(addresses)} — пропускаю их.")

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
        if ok:
            record(ledger, address)
        else:
            failures.append(address)
        if (index + 1) % 10 == 0:
            print(f"  отправлено {index + 1} из {len(addresses)}…", flush=True)
        if index + 1 < len(addresses):
            await asyncio.sleep(SEND_INTERVAL_SECONDS)

    print(f"\nИтого: доставлено {sent}, не доставлено {len(failures)}")
    for address in failures:
        print(f"  {address}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
