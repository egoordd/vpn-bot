import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from database.repository import Repository
from services import wallet
from services.http_api import create_app
from services.promo import PROMO_BALANCE_BONUS, PROMO_PERCENT_DISCOUNT


@pytest_asyncio.fixture
async def api_client(session_pool):
    # Authed-by-default client: the API now fails closed, so a token must be set
    # and sent. Auth-specific behaviour (401/503) is covered by dedicated tests.
    app = create_app()
    app.state.session_pool = session_pool
    app.state.api_token = "secret-token"
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://billing",
        headers={"Authorization": "Bearer secret-token"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def open_client(session_pool):
    # No token configured -> the API must fail CLOSED (503), never open.
    app = create_app()
    app.state.session_pool = session_pool
    app.state.api_token = ""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://billing") as client:
        yield client


@pytest.mark.asyncio
async def test_missing_token_fails_closed(open_client):
    # Every route (except the HMAC-signed webhook) must be denied when unset.
    for path in ("/health", "/plans", "/account/1", "/admin/stats"):
        resp = await open_client.get(path)
        assert resp.status_code == 503, path


@pytest.mark.asyncio
async def test_wrong_or_missing_bearer_is_401(secured_client):
    assert (await secured_client.get("/plans")).status_code == 401
    bad = await secured_client.get("/plans", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


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


@pytest.mark.asyncio
async def test_yookassa_webhook_provisions_and_delivers(api_client, session_pool, monkeypatch):
    from unittest.mock import AsyncMock

    from database.repository import Repository
    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=7777)
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id,
            amount=14900,
            external_invoice_id="yk-1",
            invoice_payload=payload,
            plan="standard_1m",
        )

    monkeypatch.setattr(
        api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-1", "status": "succeeded"})
    )

    class _Sub:
        subscription_url = "https://sub.example/sub/abc"

    monkeypatch.setattr(api_mod, "activate_panel_subscription", AsyncMock(return_value=_Sub()))
    monkeypatch.setattr(api_mod, "reward_referrer_for_payment", AsyncMock())
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", deliver)

    response = await api_client.post(
        "/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-1"}}
    )

    assert response.status_code == 200
    assert response.json()["plan"] == "standard_1m"
    deliver.assert_awaited_once()

    async with session_pool() as session:
        repo = Repository(session)
        payment = await repo.get_payment_by_external_id("yk-1")
        assert payment.status == "completed"
        counts = await repo.funnel_counts()
        assert counts.get("payment") == 1


@pytest.mark.asyncio
async def test_yookassa_webhook_ignores_unpaid(api_client, monkeypatch):
    from unittest.mock import AsyncMock

    from services import http_api as api_mod

    monkeypatch.setattr(
        api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-2", "status": "pending"})
    )
    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-2"}})

    assert response.status_code == 200
    assert response.json()["ignored"] == "pending"


@pytest.mark.asyncio
async def test_yookassa_webhook_issues_moynalog_receipt(api_client, session_pool, monkeypatch):
    from unittest.mock import AsyncMock

    from database.repository import Repository
    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=7788)
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-r1",
            invoice_payload=payload, plan="standard_1m",
        )

    monkeypatch.setattr(api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-r1", "status": "succeeded"}))

    class _Sub:
        subscription_url = "https://sub.example/sub/abc"

    monkeypatch.setattr(api_mod, "activate_panel_subscription", AsyncMock(return_value=_Sub()))
    monkeypatch.setattr(api_mod, "reward_referrer_for_payment", AsyncMock())
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", AsyncMock(return_value=True))
    monkeypatch.setattr(api_mod.moynalog, "is_configured", lambda: True)
    issue = AsyncMock(return_value="https://lknpd.nalog.ru/api/v1/receipt/x/rcpt/print")
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.moynalog, "issue_receipt", issue)
    monkeypatch.setattr(api_mod.moynalog, "deliver_receipt", deliver)

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-r1"}})

    assert response.status_code == 200
    issue.assert_awaited_once()
    assert issue.await_args.args[0] == 14900  # full amount in kopecks
    deliver.assert_awaited_once_with(7788, "https://lknpd.nalog.ru/api/v1/receipt/x/rcpt/print")


@pytest.mark.asyncio
async def test_yookassa_webhook_needs_no_bearer(secured_client, monkeypatch):
    from unittest.mock import AsyncMock

    from services import http_api as api_mod

    # exempt from the app-wide bearer check; unpaid status short-circuits before delivery
    monkeypatch.setattr(
        api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-3", "status": "canceled"})
    )
    response = await secured_client.post("/yookassa/webhook", json={"object": {"id": "yk-3"}})
    assert response.status_code == 200


# --- website checkout / order / account --------------------------------------

def _yk_payment_mock(payment_id: str = "yk-web-1"):
    from unittest.mock import AsyncMock

    return AsyncMock(
        return_value={
            "id": payment_id,
            "status": "pending",
            "confirmation": {"confirmation_url": f"https://yoomoney.ru/pay/{payment_id}"},
        }
    )


@pytest.mark.asyncio
async def test_web_checkout_with_telegram_id(api_client, session_pool, monkeypatch):
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    create = _yk_payment_mock("yk-web-1")
    monkeypatch.setattr(api_mod.yookassa, "create_payment", create)

    response = await api_client.post(
        "/web/checkout", json={"plan": "standard_1m", "telegramId": 9101}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["orderId"] == "yk-web-1"
    assert body["payUrl"] == "https://yoomoney.ru/pay/yk-web-1"
    assert body["plan"]["code"] == "standard_1m"
    assert create.await_args.kwargs["metadata"]["source"] == "web"

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(9101)
        assert user is not None
        payment = await repo.get_payment_by_external_id("yk-web-1")
        assert payment is not None
        assert payment.provider == "yookassa"
        assert payment.user_id == user.id
        assert payment.status == "pending"


@pytest.mark.asyncio
async def test_web_checkout_keeps_existing_username(api_client, session_pool, monkeypatch):
    from services import http_api as api_mod

    async with session_pool() as session:
        await Repository(session).create_user(telegram_id=9102, username="keepme")

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(api_mod.yookassa, "create_payment", _yk_payment_mock("yk-web-2"))

    response = await api_client.post(
        "/web/checkout", json={"plan": "standard_1m", "telegramId": 9102}
    )

    assert response.status_code == 200
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(9102)
        assert user.username == "keepme"


@pytest.mark.asyncio
async def test_web_checkout_with_email_creates_synthetic_user(api_client, session_pool, monkeypatch):
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    create = _yk_payment_mock("yk-web-3")
    monkeypatch.setattr(api_mod.yookassa, "create_payment", create)

    response = await api_client.post(
        "/web/checkout", json={"plan": "standard_1m", "email": "  Buyer@Mail.RU "}
    )

    assert response.status_code == 200
    assert create.await_args.kwargs["receipt_email"] == "buyer@mail.ru"

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_email("buyer@mail.ru")
        assert user is not None
        assert user.telegram_id < 0
        assert user.email == "buyer@mail.ru"

    # Second purchase with the same email reuses the account.
    monkeypatch.setattr(api_mod.yookassa, "create_payment", _yk_payment_mock("yk-web-4"))
    second = await api_client.post(
        "/web/checkout", json={"plan": "standard_1m", "email": "buyer@mail.ru"}
    )
    assert second.status_code == 200
    async with session_pool() as session:
        repo = Repository(session)
        first_payment = await repo.get_payment_by_external_id("yk-web-3")
        second_payment = await repo.get_payment_by_external_id("yk-web-4")
        assert first_payment.user_id == second_payment.user_id


@pytest.mark.asyncio
async def test_web_checkout_validation(api_client, monkeypatch):
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)

    no_identity = await api_client.post("/web/checkout", json={"plan": "standard_1m"})
    assert no_identity.status_code == 400

    bad_email = await api_client.post(
        "/web/checkout", json={"plan": "standard_1m", "email": "not-an-email"}
    )
    assert bad_email.status_code == 400

    unknown_plan = await api_client.post(
        "/web/checkout", json={"plan": "nope_9y", "telegramId": 1}
    )
    assert unknown_plan.status_code == 404

    trial = await api_client.post("/web/checkout", json={"plan": "trial", "telegramId": 1})
    assert trial.status_code == 400


@pytest.mark.asyncio
async def test_web_checkout_unavailable_without_yookassa(api_client, monkeypatch):
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: False)
    response = await api_client.post(
        "/web/checkout", json={"plan": "standard_1m", "telegramId": 1}
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_web_order_pending_then_succeeded(api_client, session_pool, monkeypatch):
    from datetime import datetime, timedelta, timezone

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=9103)
        from services.payment import create_invoice_payload

        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id,
            amount=14900,
            external_invoice_id="yk-ord-1",
            invoice_payload=payload,
            plan="standard_1m",
        )

    pending = await api_client.get("/web/order/yk-ord-1")
    assert pending.status_code == 200
    assert pending.json() == {"status": "pending"}

    now = datetime.now(timezone.utc)
    async with session_pool() as session:
        repo = Repository(session)
        await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="tg_9103",
            sub_token="tok9103",
            subscription_url="https://panel.example/sub/tok9103",
            started_at=now,
            expires_at=now + timedelta(days=30),
            is_active=True,
        )
        await repo.complete_payment_by_external_id("yk-ord-1", provider="yookassa")

    done = await api_client.get("/web/order/yk-ord-1")
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "succeeded"
    assert body["subscription"]["subscriptionUrl"] == "https://panel.example/sub/tok9103"
    assert body["subscription"]["isActive"] is True


@pytest.mark.asyncio
async def test_web_order_unknown_is_404(api_client):
    response = await api_client.get("/web/order/nope")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_web_account_by_telegram(api_client, session_pool):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=9104, username="cabinet")
        await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="tg_9104",
            sub_token="tok9104",
            subscription_url="https://panel.example/sub/tok9104",
            started_at=now,
            expires_at=now + timedelta(days=30),
            is_active=True,
        )

    response = await api_client.get("/web/account/by-telegram/9104")

    assert response.status_code == 200
    body = response.json()
    assert body["telegramId"] == 9104
    assert body["subscription"]["isActive"] is True
    assert body["subscription"]["subscriptionUrl"] == "https://panel.example/sub/tok9104"

    missing = await api_client.get("/web/account/by-telegram/424242")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_yookassa_webhook_skips_dm_for_web_email_buyer(api_client, session_pool, monkeypatch):
    from unittest.mock import AsyncMock

    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=-424242)
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id,
            amount=14900,
            external_invoice_id="yk-web-dm",
            invoice_payload=payload,
            plan="standard_1m",
        )

    monkeypatch.setattr(
        api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-web-dm", "status": "succeeded"})
    )

    class _Sub:
        subscription_url = "https://sub.example/sub/web"

    monkeypatch.setattr(api_mod, "activate_panel_subscription", AsyncMock(return_value=_Sub()))
    monkeypatch.setattr(api_mod, "reward_referrer_for_payment", AsyncMock())
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", deliver)

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-web-dm"}})

    assert response.status_code == 200
    deliver.assert_not_awaited()

    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("yk-web-dm")
        assert payment.status == "completed"
