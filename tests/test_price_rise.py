"""Повышение цен с 26.09.2026 00:00 МСК: само, без перезапуска и без потерь оплат."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services import billing_api, tariffs
from services.payment import create_invoice_payload
from tests.test_http_api import api_client  # noqa: F401 - fixture

AFTER = tariffs.PRICE_RISE_AT + timedelta(minutes=1)


def _at(monkeypatch, moment):
    monkeypatch.setattr(tariffs, "_now", lambda: moment)


@pytest.mark.unit
def test_old_prices_hold_until_midnight_moscow(monkeypatch):
    _at(monkeypatch, tariffs.PRICE_RISE_AT - timedelta(seconds=1))
    assert [tariffs.TARIFFS[c].price_rub for c in ("standard_1m", "standard_3m", "standard_6m", "standard_12m")] == [
        149, 399, 699, 1199,
    ]


@pytest.mark.unit
def test_new_prices_from_midnight_moscow(monkeypatch):
    assert tariffs.PRICE_RISE_AT == datetime(2026, 9, 26, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    _at(monkeypatch, tariffs.PRICE_RISE_AT)
    got = {
        c: (t.price_rub, t.crypto_amount)
        for c, t in tariffs.TARIFFS.items()
        if c != "trial" and not t.hidden
    }
    assert got == {
        "standard_1m": (199, "2.49"),
        "standard_3m": (549, "6.99"),
        "standard_6m": (999, "11.99"),
        "standard_12m": (1799, "19.99"),
    }
    assert tariffs.resolve_tariff("1m").price_rub == 199
    assert billing_api.get_billing_plan("standard_12m").price_rub == 1799


@pytest.mark.unit
def test_the_rise_touches_only_prices(monkeypatch):
    before = {c: t for c, t in tariffs.TARIFFS.items()}
    _at(monkeypatch, AFTER)
    for code, tariff in tariffs.TARIFFS.items():
        old = before[code]
        assert (tariff.duration_days, tariff.traffic_gb, tariff.device_limit, tariff.title) == (
            old.duration_days, old.traffic_gb, old.device_limit, old.title,
        )
    assert tariffs.TARIFFS["trial"].price_rub == 0


@pytest.mark.asyncio
async def test_an_invoice_issued_before_midnight_still_grants_after_it(api_client, session_pool, monkeypatch):  # noqa: F811
    """Счёт на 149 ₽ выставлен в 23:59, оплачен в 00:01 — подписка выдаётся."""
    from services import http_api as api_mod
    from tests.test_payment_retry import _Redis, _Sub, _yookassa_paid

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=880901)
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-rise-1",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_1m"),
            plan="standard_1m",
        )
    _at(monkeypatch, AFTER)
    api_client._transport.app.state.redis = _Redis()
    _yookassa_paid(monkeypatch, api_mod, "yk-rise-1")
    activate = AsyncMock(return_value=_Sub())
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", AsyncMock(return_value=True))

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-rise-1"}})

    assert response.status_code == 200
    assert response.json().get("error") != "amount_mismatch"
    activate.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_real_underpayment_is_still_refused(api_client, session_pool, monkeypatch):  # noqa: F811
    """Сверка не ослабла: счёт на 199 ₽, а пришло 149 — подписку не выдаём."""
    from services import http_api as api_mod
    from tests.test_payment_retry import _Redis, _Sub, _yookassa_paid

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=880902)
        await repo.create_yookassa_payment(
            user_id=user.id, amount=19900, external_invoice_id="yk-rise-2",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_1m"),
            plan="standard_1m",
        )
    _at(monkeypatch, AFTER)
    api_client._transport.app.state.redis = _Redis()
    _yookassa_paid(monkeypatch, api_mod, "yk-rise-2")
    activate = AsyncMock(return_value=_Sub())
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-rise-2"}})

    assert response.json().get("error") == "amount_mismatch"
    activate.assert_not_awaited()
