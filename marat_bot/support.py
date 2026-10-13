"""Поддержка прямо в боте (13.10.2026): обращение → администраторам, ответ → обратно пользователю.

Платёжный провайдер не принимает группу как контакт поддержки — нужен тикет, ник или почта.
Пользователь жмёт «💬 Поддержка», и следующие его сообщения (текст, фото, файлы) уходят
администраторам бота (MARAT_ADMINS) копией: первое — с карточкой «кто пишет», остальные —
ответом на неё. Админ отвечает реплаем на карточку или на копию — ответ копией приходит
пользователю, и окно обращения снова открыто. Связь «сообщение у админа → пользователь»
хранится в базе, поэтому ответить можно и после перезапуска бота.
Если ни одного админа нет (бот другого заказчика без MARAT_ADMINS), поддержка — заглушка.
"""
from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass, field

from marat_bot import admin
from marat_bot.core import Store

log = logging.getLogger("marat_bot.support")

WINDOW_SECONDS = 30 * 60
MAX_MESSAGES = 10  # за одно окно — защита админов от флуда

PROMPT = (
    "💬 <b>Поддержка</b>\n\n"
    "Опишите вопрос одним или несколькими сообщениями — можно приложить скриншот.\n"
    "Ответ придёт в этот чат, обычно в течение нескольких часов, не позднее 24 часов."
)
SENT = "✅ Передали в поддержку. Ответ придёт сюда же — можно дописать детали следующим сообщением."
LIMIT = "⏳ Сообщений уже много — дождитесь ответа поддержки, пожалуйста."
FAILED = "Не получилось передать сообщение — попробуйте ещё раз через минуту."
ANSWER = "💬 <b>Ответ поддержки</b>"


@dataclass
class _Window:
    deadline: float
    sent: int = 0
    cards: dict[int, int] = field(default_factory=dict)  # чат админа → id карточки обращения


_windows: dict[int, _Window] = {}


def recipients(store: Store) -> list[int]:
    """Кому уходят обращения: админы по ID и по нику (ник — после привязки к ID первым сообщением)."""
    bound = {store.admin_id(name) for name in admin.ADMIN_NAMES}
    return sorted(admin.ADMIN_IDS | {uid for uid in bound if uid is not None})


def available(store: Store) -> bool:
    return bool(recipients(store))


def open_window(user: int, now: float | None = None, answered: bool = False) -> None:
    """Открыть или продлить окно. Счётчик сообщений обнуляет только ответ поддержки (answered)."""
    now = time.time() if now is None else now
    current = _windows.get(user)
    if current and current.deadline > now:
        current.deadline = now + WINDOW_SECONDS
        if answered:
            current.sent = 0
        return
    _windows[user] = _Window(deadline=now + WINDOW_SECONDS)


def close(user: int) -> None:
    _windows.pop(user, None)


def is_open(user: int, now: float | None = None) -> bool:
    window = _windows.get(user)
    if window is None:
        return False
    if window.deadline <= (time.time() if now is None else now):
        close(user)
        return False
    return True


def _card(message: dict, store: Store) -> str:
    sender = message.get("from", {})
    user = sender.get("id")
    name = html.escape(sender.get("first_name") or "без имени")
    nick = f" · @{html.escape(sender['username'])}" if sender.get("username") else ""
    account = store.get(user) if isinstance(user, int) else None
    return (
        "🆘 <b>Обращение в поддержку</b>\n"
        f"{name}{nick}\n"
        f"ID <code>{user}</code> · учётка <code>{html.escape(account or '—')}</code>\n\n"
        "Ответьте на это сообщение (реплаем) — ответ уйдёт пользователю."
    )


async def forward(tg, store: Store, message: dict) -> str:
    """Переслать сообщение пользователя админам. Возвращает текст для пользователя."""
    user = message["from"]["id"]
    window = _windows.get(user)
    if window is None:
        return FAILED
    if window.sent >= MAX_MESSAGES:
        return LIMIT
    delivered = 0
    for chat in recipients(store):
        try:
            card = window.cards.get(chat)
            if card is None:
                sent = await tg.send(chat, _card(message, store))
                card = sent["message_id"]
                window.cards[chat] = card
                store.link_support(chat, card, user)
            copy = await tg.copy(chat, message["chat"]["id"], message["message_id"], reply_to=card)
            store.link_support(chat, copy, user)
            delivered += 1
        except Exception:
            log.exception("support: message from %s not delivered to admin %s", user, chat)
    if not delivered:
        return FAILED
    window.sent += 1
    log.info("support: message from %s delivered to %d admin(s)", user, delivered)
    return SENT


async def reply(tg, store: Store, message: dict, markup: dict) -> bool:
    """Ответ админа реплаем на обращение → пользователю. False — это не ответ на обращение."""
    target = message.get("reply_to_message") or {}
    chat = message["chat"]["id"]
    user = store.support_user(chat, target.get("message_id", 0)) if target else None
    if user is None:
        return False
    try:
        await tg.send(user, ANSWER)
        await tg.copy(user, chat, message["message_id"], markup=markup)
    except Exception:
        log.exception("support: answer to %s not delivered", user)
        await tg.send(chat, "❌ Не доставлено — возможно, пользователь остановил бота.")
        return True
    open_window(user, answered=True)
    log.info("support: admin %s answered %s", chat, user)
    await tg.send(chat, "✅ Ответ отправлен.")
    return True
