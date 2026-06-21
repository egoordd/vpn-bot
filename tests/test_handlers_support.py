from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import support


@pytest.mark.unit
async def test_support_handler_links_to_support_bot(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_BOT_USERNAME", "unlock_support_bot")
    shown = {}

    async def fake_show(callback, text, keyboard):
        shown["text"] = text
        shown["keyboard"] = keyboard

    monkeypatch.setattr(support, "show_screen", fake_show)
    callback = SimpleNamespace(from_user=SimpleNamespace(id=42), answer=AsyncMock())

    await support.support_handler(callback)

    urls = [b.url for row in shown["keyboard"].inline_keyboard for b in row if b.url]
    assert any("unlock_support_bot" in u for u in urls)
    callback.answer.assert_awaited_once()
