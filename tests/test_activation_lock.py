"""Две одновременные оплаты одного клиента — два периода (аудит 22.09.2026, BILL-03)."""

import asyncio
from datetime import datetime, timezone

import pytest

from database.repository import Repository
from services import activation_lock
from services.subscription import _aware, activate_panel_subscription
from tests.test_subscription import FakeGenericPanelGateway


class SlowPanel(FakeGenericPanelGateway):
    """Панель отвечает не сразу — выдачи успевают переплестись."""

    async def get_user(self, username: str):
        await asyncio.sleep(0.01)
        return await super().get_user(username)

    async def modify_user(self, **kwargs):
        await asyncio.sleep(0.01)
        return await super().modify_user(**kwargs)


@pytest.mark.integration
async def test_two_payments_at_once_add_two_periods(session_pool):
    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=7301)
    panel = SlowPanel(exists=True)
    before = datetime.now(timezone.utc)

    async def pay() -> None:
        async with session_pool() as session:
            await activate_panel_subscription(session, user.id, "standard_1m", panel_gateway=panel)

    await asyncio.gather(pay(), pay())

    async with session_pool() as session:
        latest = await Repository(session).get_latest_standard_subscription(user.id)
    days = (_aware(latest.expires_at) - before).days
    assert days >= 59, f"две оплаты по месяцу дали {days} дн."
    assert activation_lock._local_locks == {}


@pytest.mark.unit
async def test_other_clients_are_not_blocked():
    order: list[str] = []

    class FakeSession:
        bind = None

    async def activate(user_id: int, name: str) -> None:
        async with activation_lock.user_activation_lock(FakeSession(), user_id):
            order.append(f"{name}:start")
            await asyncio.sleep(0.02)
            order.append(f"{name}:end")

    await asyncio.gather(activate(1, "a"), activate(2, "b"))

    assert order[:2] == ["a:start", "b:start"]


@pytest.mark.unit
async def test_lock_is_released_when_activation_fails():
    class FakeSession:
        bind = None

    with pytest.raises(RuntimeError):
        async with activation_lock.user_activation_lock(FakeSession(), 5):
            raise RuntimeError("panel down")

    async with activation_lock.user_activation_lock(FakeSession(), 5):
        pass
    assert activation_lock._local_locks == {}

