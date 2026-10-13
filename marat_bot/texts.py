"""Тексты бота — из темы, которую выбирает служба (MARAT_THEME, по умолчанию classic).

С 14.10.2026 тема может знать несколько языков (LANGUAGES, localized(lang)): тогда на время
обработки одного обновления use(lang) выбирает набор текстов человека, а current() отдаёт
его клавиатурам и обработчикам. У темы без языков всё как раньше — этот модуль и есть набор.
"""
from __future__ import annotations

import contextvars
import os
import sys

from marat_bot.themes import INTERFACE, load

THEME = os.environ.get("MARAT_THEME", "classic").strip() or "classic"
_theme = load(THEME)
globals().update({name: getattr(_theme, name) for name in INTERFACE})
# Баннеры экранов — только у тем с картинками; без них бот шлёт обычный текст.
BANNERS: dict[str, str] = getattr(_theme, "BANNERS", {})
# Языки интерфейса темы: {код: (флаг, название)}; пусто — бот одноязычный.
LANGUAGES: dict[str, tuple[str, str]] = getattr(_theme, "LANGUAGES", {})

_current: contextvars.ContextVar = contextvars.ContextVar("marat_texts", default=None)


def localized(lang: str | None):
    if LANGUAGES and lang in LANGUAGES:
        return _theme.localized(lang)
    return sys.modules[__name__]


def use(lang: str | None):
    """Набор текстов для этого обновления (asyncio-задача видит только свой)."""
    texts = localized(lang)
    _current.set(texts)
    return texts


def current():
    return _current.get() or sys.modules[__name__]
