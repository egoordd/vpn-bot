from unittest.mock import AsyncMock

import pytest

from services import alerts


@pytest.mark.unit
async def test_send_alert_disabled_without_token(monkeypatch):
    monkeypatch.setattr(alerts.settings, "ALERTS_BOT_TOKEN", "")
    post = AsyncMock()
    monkeypatch.setattr(alerts, "_post", post)

    assert await alerts.send_alert("hi") is False
    post.assert_not_awaited()


@pytest.mark.unit
async def test_send_alert_success(monkeypatch):
    monkeypatch.setattr(alerts.settings, "ALERTS_BOT_TOKEN", "tok")
    monkeypatch.setattr(alerts.settings, "ALERTS_CHAT_ID", "123")
    monkeypatch.setattr(alerts, "_post", AsyncMock(return_value=200))

    assert await alerts.send_alert("hi") is True


@pytest.mark.unit
async def test_send_alert_throttles_repeat(monkeypatch):
    monkeypatch.setattr(alerts.settings, "ALERTS_BOT_TOKEN", "tok")
    monkeypatch.setattr(alerts.settings, "ALERTS_CHAT_ID", "123")
    post = AsyncMock(return_value=200)
    monkeypatch.setattr(alerts, "_post", post)
    alerts._last_sent.clear()

    assert await alerts.send_alert("x", throttle_key="k") is True
    assert await alerts.send_alert("x", throttle_key="k") is False
    assert post.await_count == 1
