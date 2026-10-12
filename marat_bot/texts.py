"""Тексты бота — из темы, которую выбирает служба (MARAT_THEME, по умолчанию classic)."""
from __future__ import annotations

import os

from marat_bot.themes import INTERFACE, load

THEME = os.environ.get("MARAT_THEME", "classic").strip() or "classic"
_theme = load(THEME)
globals().update({name: getattr(_theme, name) for name in INTERFACE})
