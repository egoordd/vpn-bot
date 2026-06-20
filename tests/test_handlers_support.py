from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import support


@pytest.mark.unit
async def test_support_receive_forwards_to_alerts(monkeypatch):
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(support, "send_alert", send)
    state = AsyncMock()
    message = SimpleNamespace(
        text="не работает подключение",
        caption=None,
        from_user=SimpleNamespace(id=555, username="bob", full_name="Bob B"),
        answer=AsyncMock(),
    )

    await support.support_receive(message, state)

    state.clear.assert_awaited_once()
    send.assert_awaited_once()
    sent = send.await_args.args[0]
    assert "555" in sent
    assert "не работает подключение" in sent
    message.answer.assert_awaited_once()


@pytest.mark.unit
async def test_support_receive_ignores_empty(monkeypatch):
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(support, "send_alert", send)
    state = AsyncMock()
    message = SimpleNamespace(
        text="",
        caption=None,
        from_user=SimpleNamespace(id=5, username=None, full_name=None),
        answer=AsyncMock(),
    )

    await support.support_receive(message, state)

    send.assert_not_awaited()
