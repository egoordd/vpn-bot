"""Shared text formatting for bot screens.

Single place for the visual language: blockquote info cards, Moscow-time
dates, traffic numbers. Every handler builds its cards from these helpers so
the bot looks consistent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

_GB = 1024 ** 3


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_msk(value: datetime) -> str:
    msk = aware(value) + timedelta(hours=3)
    return f"{msk.day:02d} {MONTHS_RU[msk.month - 1]} {msk.year} года, {msk:%H:%M} (МСК)"


def format_gb(value_bytes: int | None) -> str:
    if value_bytes is None:
        return "∞"
    gb = value_bytes / _GB
    return f"{gb:.1f}".rstrip("0").rstrip(".") or "0"


def bq(*lines: str) -> str:
    """Wrap lines into a Telegram blockquote card."""
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


def plural_days(count: int) -> str:
    """`5 дней`, `2 дня`, `1 день` — Russian counting, so copy can be derived.

    The trial length was written out by hand in thirteen places; changing it
    from three days to seven meant editing every one of them. Deriving the
    words means the next change is one number.
    """
    tail = abs(count) % 100
    if 11 <= tail <= 14:
        word = "дней"
    else:
        last = tail % 10
        word = "день" if last == 1 else "дня" if 2 <= last <= 4 else "дней"
    return f"{count} {word}"


def trial_days() -> str:
    from services.tariffs import resolve_tariff

    return plural_days(resolve_tariff("trial").duration_days)
