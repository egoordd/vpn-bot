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


@pytest.mark.unit
async def test_send_alert_reaches_every_staff_chat(monkeypatch):
    """19.09.2026: уведомления получает и помощник владельца (@edismee)."""
    monkeypatch.setattr(alerts.settings, "ALERTS_BOT_TOKEN", "tok")
    monkeypatch.setattr(alerts.settings, "ALERTS_CHAT_ID", "740484324")
    monkeypatch.setattr(alerts.settings, "ALERTS_EXTRA_CHAT_IDS", "8563480666, 740484324")
    post = AsyncMock(return_value=200)
    monkeypatch.setattr(alerts, "_post", post)
    alerts._last_sent.clear()

    assert await alerts.send_alert("оплата") is True
    assert [call.args[1]["chat_id"] for call in post.await_args_list] == ["740484324", "8563480666"]


@pytest.mark.unit
async def test_one_unreachable_staff_chat_does_not_stop_the_rest(monkeypatch):
    monkeypatch.setattr(alerts.settings, "ALERTS_BOT_TOKEN", "tok")
    monkeypatch.setattr(alerts.settings, "ALERTS_CHAT_ID", "740484324")
    monkeypatch.setattr(alerts.settings, "ALERTS_EXTRA_CHAT_IDS", "8563480666")
    post = AsyncMock(side_effect=[403, 200])
    monkeypatch.setattr(alerts, "_post", post)
    alerts._last_sent.clear()

    assert await alerts.send_alert("оплата") is True
    assert post.await_count == 2
