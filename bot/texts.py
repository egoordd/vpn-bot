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
