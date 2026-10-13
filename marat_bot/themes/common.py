"""Общее для тем: цитаты, приветствие, карточка доступа с иконками темы."""
from __future__ import annotations

import html
from dataclasses import dataclass

from marat_bot.core import DEVICES, TRIAL_DAYS, TRIAL_TRAFFIC_BYTES, Access, bar, date_msk, days_word, gb, time_left

FLAGS = "🇵🇱 🇫🇮 🇳🇱 🇺🇸"
TRIAL = days_word(TRIAL_DAYS)
TRIAL_GB = TRIAL_TRAFFIC_BYTES // 1024**3
# Документы и поддержка (13.10.2026, требование платёжного провайдера) — одинаковые во всех темах.
DOC_BUTTONS = {
    "docs": "📄 Документы",
    "privacy": "🔒 Политика конфиденциальности",
    "terms": "📜 Пользовательское соглашение",
    "site_tariffs": "💳 Тарифы и оплата на сайте",
    "pay_terms": "📜 Условия оплаты и возврата",
    "support_cancel": "← Отменить",
    "support_reply": "✍️ Ответить поддержке",
    "app": "📱 Открыть приложение",
}


def quote(*lines: str, expandable: bool = False) -> str:
    tag = "blockquote expandable" if expandable else "blockquote"
    return f"<{tag}>" + "\n".join(lines) + "</blockquote>"


def escape_name(name: str | None) -> str | None:
    return html.escape(name) if name else None


@dataclass(frozen=True)
class Look:
    """Строки карточки доступа. {left}, {date}, {bar}, {used}, {limit}, {devices} подставляются."""

    active: str
    expired: str
    limited: str
    left: str
    until: str
    was_until: str
    traffic: str
    traffic_unlimited: str
    devices: str
    full: str = "▰"
    empty: str = "▱"


def card(access: Access, look: Look) -> list[str]:
    """Первая строка — состояние; дальше срок, трафик, устройства."""
    if access.active:
        lines = [look.active]
        if access.expire:
            lines += [look.left.format(left=time_left(access.expire)), look.until.format(date=date_msk(access.expire))]
    else:
        lines = [look.limited if access.status == "limited" else look.expired]
        if access.expire:
            lines.append(look.was_until.format(date=date_msk(access.expire)))
    if access.limit_bytes:
        lines.append(look.traffic.format(
            bar=bar(access.used_bytes, access.limit_bytes, full=look.full, empty=look.empty),
            used=gb(access.used_bytes), limit=gb(access.limit_bytes),
        ))
    else:
        lines.append(look.traffic_unlimited.format(used=gb(access.used_bytes)))
    return [*lines, look.devices.format(devices=DEVICES)]


COMMAND_LINES = (
    "/start — главное меню",
    "/connect — подключить устройство",
    "/status — срок, трафик и ссылка подписки",
    "/tariffs — тарифы",
    "/promo — ввести промокод",
    "/support — поддержка",
    "/help — эта справка",
)
