import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from database.repository import Repository
from services import wallet
from services.http_api import create_app
from services.promo import PROMO_BALANCE_BONUS, PROMO_PERCENT_DISCOUNT


@pytest_asyncio.fixture
async def api_client(session_pool):
    app = create_app()
    app.state.session_pool = session_pool
    app.state.api_token = ""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://billing") as client:
        yield client


@pytest_asyncio.fixture
async def secured_client(session_pool):
    app = create_app()
    app.state.session_pool = session_pool
    app.state.api_token = "secret-token"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://billing") as client:
        yield client


async def _user(session_pool, telegram_id: int = 9001):
    async with session_pool() as session:
        return await Repository(session).create_user(telegram_id=telegram_id, username="webuser")


@pytest.mark.asyncio
async def test_health(api_client):
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_plans_returns_camelcase_catalogue(api_client):
    response = await api_client.get("/plans")

    assert response.status_code == 200
    plans = response.json()["plans"]
    codes = [plan["code"] for plan in plans]
    assert "trial" not in codes
    assert "standard_1m" in codes
    sample = plans[0]
    assert {"code", "title", "tier", "durationDays", "priceRub", "trafficLimitBytes"} <= set(sample)


@pytest.mark.asyncio
async def test_plans_filters_by_tier(api_client):
    response = await api_client.get("/plans", params={"tier": "premium"})
    plans = response.json()["plans"]
    assert plans and all(plan["tier"] == "premium" for plan in plans)


@pytest.mark.asyncio
async def test_regions(api_client):
    response = await api_client.get("/regions")
    assert response.status_code == 200
    regions = response.json()["regions"]
    assert regions and {"code", "title", "city", "countryCode", "isOnDemand"} <= set(regions[0])


@pytest.mark.asyncio
async def test_account_unknown_user_404(api_client):
    response = await api_client.get("/account/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "user_not_found"


@pytest.mark.asyncio
async def test_account_overview_camelcase(api_client, session_pool):
    user = await _user(session_pool)
    async with session_pool() as session:
        await wallet.deposit(session, user.id, 14900, reference="topup-web")

    response = await api_client.get(f"/account/{user.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["userId"] == user.id
    assert body["telegramId"] == user.telegram_id
    assert body["wallet"]["balanceKopecks"] == 14900
    assert body["wallet"]["entries"][0]["amountKopecks"] == 14900
    assert body["subscription"]["exists"] is False
    assert body["referral"]["rewardPercent"] == 20
    assert "balanceDisplay" in body


@pytest.mark.asyncio
async def test_promo_preview_returns_discount(api_client, session_pool):
    user = await _user(session_pool)
    async with session_pool() as session:
        await Repository(session).create_promo_code(
            code="MINUS20", kind=PROMO_PERCENT_DISCOUNT, value=20
        )

    response = await api_client.post(
        "/promo/preview",
        json={"userId": user.id, "code": "MINUS20", "amountKopecks": 14900},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": "MINUS20",
        "originalKopecks": 14900,
        "discountKopecks": 2980,
        "finalKopecks": 11920,
    }


@pytest.mark.asyncio
async def test_promo_preview_unknown_code_404(api_client, session_pool):
    user = await _user(session_pool)
    response = await api_client.post(
        "/promo/preview",
        json={"userId": user.id, "code": "GHOST", "amountKopecks": 14900},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "promo_not_found"


@pytest.mark.asyncio
async def test_promo_preview_wrong_type_400(api_client, session_pool):
    user = await _user(session_pool)
    async with session_pool() as session:
        await Repository(session).create_promo_code(
            code="BONUS", kind=PROMO_BALANCE_BONUS, value=5000
        )

    response = await api_client.post(
        "/promo/preview",
        json={"userId": user.id, "code": "BONUS", "amountKopecks": 14900},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "promo_wrong_type"


@pytest.mark.asyncio
async def test_promo_preview_validates_body(api_client):
    response = await api_client.post(
        "/promo/preview",
        json={"userId": 1, "code": "", "amountKopecks": -5},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_auth_required_when_token_configured(secured_client):
    denied = await secured_client.get("/plans")
    assert denied.status_code == 401

    allowed = await secured_client.get(
        "/plans", headers={"Authorization": "Bearer secret-token"}
    )
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_admin_stats_returns_aggregates(api_client, session_pool):
    await _user(session_pool, telegram_id=9100)

    response = await api_client.get("/admin/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["users"]["total"] >= 1
    assert "activeByTier" in data["subscriptions"]
    assert "balancesKopecks" in data["money"] and "depositsKopecks" in data["money"]
    assert isinstance(data["recent"], list)


@pytest.mark.asyncio
async def test_tribute_webhook_provisions_and_delivers(api_client, monkeypatch):
    from unittest.mock import AsyncMock

    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.tribute, "verify_signature", lambda raw, sig: True)
    monkeypatch.setattr(api_mod.tribute, "plan_for", lambda tid: "standard_1m")
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", deliver)

    class _Sub:
        subscription_url = "https://sub.example/sub/abc"

    activate = AsyncMock(return_value=_Sub())
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)

    body = {
        "name": "new_digital_product",
        "payload": {"telegram_user_id": 555, "product_id": 1, "purchase_id": "p1", "telegram_username": "@buyer"},
    }
    response = await api_client.post("/tribute/webhook", json=body, headers={"trbt-signature": "x"})

    assert response.status_code == 200
    assert response.json()["plan"] == "standard_1m"
    activate.assert_awaited_once()
    assert activate.await_args.kwargs["plan"] == "standard_1m"
    deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_tribute_webhook_rejects_bad_signature(api_client, monkeypatch):
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.tribute, "verify_signature", lambda raw, sig: False)
    response = await api_client.post("/tribute/webhook", json={"name": "x"}, headers={"trbt-signature": "bad"})
    assert response.status_code == 401
