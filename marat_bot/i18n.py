"""Языки интерфейса бота (14.10.2026, первым — «Avangard VPN»): ru, en, uk, zh, fa.

Здесь — то, что зависит от языка, но не от темы: «3 дня», «2 дня 14 ч», дата
окончания доступа и первая догадка о языке по настройкам Telegram. Тексты экранов —
в теме (themes/avangard.py → localized(lang)).
"""
from __future__ import annotations

import time
from datetime import datetime

from marat_bot.core import MSK, date_msk, days_word, time_left

LANGS = ("ru", "en", "uk", "zh", "fa")

_MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"),
    "uk": ("січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня",
           "листопада", "грудня"),
    "fa": ("ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"),
}


def guess(language_code: str | None) -> str:
    """Язык по настройкам Telegram: русскоязычные — ru, остальные известные — свои, прочие — en."""
    code = (language_code or "").lower().split("-")[0]
    if code in ("ru", "be", "kk", "ky", "uz", "tg", "hy", "az"):
        return "ru"
    return code if code in LANGS else "en"


def days(n: int, lang: str = "ru") -> str:
    if lang == "ru":
        return days_word(n)
    if lang == "uk":
        tail, last = n % 100, n % 10
        word = "днів" if 11 <= tail <= 14 else "день" if last == 1 else "дні" if 2 <= last <= 4 else "днів"
        return f"{n} {word}"
    if lang == "zh":
        return f"{n} 天"
    if lang == "fa":
        return f"{n} روز"
    return f"{n} day" if n == 1 else f"{n} days"


_UNITS = {  # (часы, минуты, «меньше минуты»)
    "en": ("h", "min", "less than a minute"),
    "uk": ("год", "хв", "менше хвилини"),
    "zh": ("小时", "分钟", "不到一分钟"),
    "fa": ("ساعت", "دقیقه", "کمتر از یک دقیقه"),
}


def left(expire: int, lang: str = "ru", now: float | None = None) -> str:
    """Сколько осталось: «2 дня 14 ч» / «2 days 14 h» / «2 天 14 小时»."""
    if lang == "ru":
        return time_left(expire, now)
    hour, minute, tiny = _UNITS[lang]
    seconds = int(expire - (now if now is not None else time.time()))
    if seconds <= 0:
        return f"0 {minute}"
    d, rest = divmod(seconds, 86400)
    h, m = rest // 3600, rest % 3600 // 60
    if d:
        return f"{days(d, lang)} {h} {hour}" if h else days(d, lang)
    if h:
        return f"{h} {hour} {m} {minute}" if m else f"{h} {hour}"
    return f"{m} {minute}" if m else tiny


def date_text(ts: int, lang: str = "ru") -> str:
    """Дата окончания по Москве: «15 октября, 12:00 МСК» на языке интерфейса."""
    if lang == "ru":
        return date_msk(ts)
    moment = datetime.fromtimestamp(ts, MSK)
    clock = f"{moment:%H:%M}"
    if lang == "zh":
        return f"{moment.month}月{moment.day}日 {clock}（莫斯科时间）"
    if lang == "fa":
        return f"{moment.day} {_MONTHS['fa'][moment.month - 1]}، {clock} (به وقت مسکو)"
    if lang == "uk":
        return f"{moment.day} {_MONTHS['uk'][moment.month - 1]}, {clock} за Москвою"
    return f"{moment.day} {_MONTHS['en'][moment.month - 1]}, {clock} Moscow time"
