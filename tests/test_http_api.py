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
    deliver_email = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.moynalog, "issue_receipt", issue)
    monkeypatch.setattr(api_mod.moynalog, "deliver_receipt", deliver)
    monkeypatch.setattr(api_mod.moynalog, "deliver_receipt_email", deliver_email)

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-r1"}})

    assert response.status_code == 200
    issue.assert_awaited_once()
    assert issue.await_args.args[0] == 14900  # full amount in kopecks
    deliver.assert_awaited_once_with(7788, "https://lknpd.nalog.ru/api/v1/receipt/x/rcpt/print")
    deliver_email.assert_not_awaited()  # buyer has no saved email


@pytest.mark.asyncio
async def test_yookassa_webhook_emails_receipt_to_email_buyer(api_client, session_pool, monkeypatch):
    from unittest.mock import AsyncMock

    from database.repository import Repository
    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    # Site email-only buyer: synthetic negative telegram_id, email on file.
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=-424242)
        await repo.update_user(user.id, email="buyer@example.com")
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-r2",
            invoice_payload=payload, plan="standard_1m",
        )

    monkeypatch.setattr(api_mod.yookassa, "get_payment", AsyncMock(return_value={"id": "yk-r2", "status": "succeeded"}))

    class _Sub:
        subscription_url = "https://sub.example/sub/abc"

    monkeypatch.setattr(api_mod, "activate_panel_subscription", AsyncMock(return_value=_Sub()))
    monkeypatch.setattr(api_mod, "reward_referrer_for_payment", AsyncMock())
    dm_sub = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", dm_sub)
    monkeypatch.setattr(api_mod.moynalog, "is_configured", lambda: True)
    issue = AsyncMock(return_value="https://lknpd.nalog.ru/api/v1/receipt/x/rcpt2/print")
    deliver = AsyncMock(return_value=True)
    deliver_email = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.moynalog, "issue_receipt", issue)
    monkeypatch.setattr(api_mod.moynalog, "deliver_receipt", deliver)
    monkeypatch.setattr(api_mod.moynalog, "deliver_receipt_email", deliver_email)

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-r2"}})

    assert response.status_code == 200
    dm_sub.assert_not_awaited()  # negative id — never DM
    deliver.assert_not_awaited()
    deliver_email.assert_awaited_once_with(
        "buyer@example.com", "https://lknpd.nalog.ru/api/v1/receipt/x/rcpt2/print"
    )


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


@pytest.mark.asyncio
async def test_web_account_email_update(api_client, session_pool):
    async with session_pool() as session:
        await Repository(session).create_user(telegram_id=9105, username="emailweb")

    response = await api_client.post(
        "/web/account/email", json={"telegramId": 9105, "email": "  Web@Mail.RU "}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "email": "web@mail.ru"}
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(9105)
        assert user.email == "web@mail.ru"

    bad = await api_client.post(
        "/web/account/email", json={"telegramId": 9105, "email": "nope"}
    )
    assert bad.status_code == 400

    missing = await api_client.post(
        "/web/account/email", json={"telegramId": 424243, "email": "a@b.ru"}
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_web_account_payload_includes_email(api_client, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=9106, username="emailshow")
        await repo.update_user(user.id, email="shown@mail.ru")

    response = await api_client.get("/web/account/by-telegram/9106")

    assert response.status_code == 200
    assert response.json()["email"] == "shown@mail.ru"


def _yk_unique_payment_mock(prefix: str):
    from unittest.mock import AsyncMock

    counter = {"n": 0}

    async def create(**kwargs):
        counter["n"] += 1
        pid = f"{prefix}-{counter['n']}"
        return {"id": pid, "status": "pending", "confirmation": {"confirmation_url": f"https://yoomoney.ru/pay/{pid}"}}

    return AsyncMock(side_effect=create)


class _FakeRedis:
    """Minimal async Redis stand-in for rate-limit + idempotency tests."""

    def __init__(self):
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


@pytest.mark.asyncio
async def test_web_checkout_rate_limited_per_ip(api_client, session_pool, monkeypatch):
    from services import http_api as api_mod

    api_client._transport.app.state.redis = _FakeRedis()
    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(api_mod.yookassa, "create_payment", _yk_unique_payment_mock("yk-rl"))

    headers = {"x-client-ip": "203.0.113.9"}
    ok_count = 0
    limited = False
    for i in range(api_mod._CHECKOUT_IP_LIMIT + 2):
        # Vary identity so the per-IP bucket (not the per-id bucket) is what trips.
        resp = await api_client.post(
            "/web/checkout",
            json={"plan": "standard_1m", "email": f"buyer{i}@mail.ru"},
            headers=headers,
        )
        if resp.status_code == 429:
            limited = True
            break
        assert resp.status_code == 200
        ok_count += 1

    assert limited
    assert ok_count == api_mod._CHECKOUT_IP_LIMIT


@pytest.mark.asyncio
async def test_web_checkout_rate_limited_per_email(api_client, session_pool, monkeypatch):
    from services import http_api as api_mod

    api_client._transport.app.state.redis = _FakeRedis()
    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(api_mod.yookassa, "create_payment", _yk_unique_payment_mock("yk-rl2"))

    last = None
    for i in range(api_mod._CHECKOUT_ID_LIMIT + 2):
        last = await api_client.post(
            "/web/checkout",
            json={"plan": "standard_1m", "email": "same@mail.ru"},
            headers={"x-client-ip": f"198.51.100.{i}"},
        )
    assert last.status_code == 429


@pytest.mark.asyncio
async def test_web_checkout_not_limited_without_redis(api_client, monkeypatch):
    # Redis absent → fail open, real purchases must never be blocked.
    from services import http_api as api_mod

    api_client._transport.app.state.redis = None
    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    monkeypatch.setattr(api_mod.yookassa, "create_payment", _yk_unique_payment_mock("yk-noredis"))

    for i in range(api_mod._CHECKOUT_IP_LIMIT + 3):
        resp = await api_client.post(
            "/web/checkout",
            json={"plan": "standard_1m", "email": f"free{i}@mail.ru"},
            headers={"x-client-ip": "203.0.113.10"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_yookassa_webhook_rejects_amount_mismatch(api_client, session_pool, monkeypatch):
    from unittest.mock import AsyncMock

    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=7799)
        payload = create_invoice_payload(user_id=user.id, plan="standard_1m")
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-amt",
            invoice_payload=payload, plan="standard_1m",
        )

    # YooKassa reports a paid amount far below the plan price (1.00 ₽).
    monkeypatch.setattr(
        api_mod.yookassa,
        "get_payment",
        AsyncMock(return_value={"id": "yk-amt", "status": "succeeded", "amount": {"value": "1.00"}}),
    )
    activate = AsyncMock()
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)
    deliver = AsyncMock()
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", deliver)

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-amt"}})

    assert response.status_code == 200
    assert response.json()["error"] == "amount_mismatch"
    activate.assert_not_awaited()
    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_auth_register_and_login_endpoints(api_client, session_pool):
    reg = await api_client.post(
        "/web/auth/register", json={"email": "webacct@mail.ru", "password": "supersecret1"}
    )
    assert reg.status_code == 200
    tid = reg.json()["telegramId"]
    assert tid < 0

    dup = await api_client.post(
        "/web/auth/register", json={"email": "webacct@mail.ru", "password": "supersecret1"}
    )
    assert dup.status_code == 409

    good = await api_client.post(
        "/web/auth/login", json={"email": "webacct@mail.ru", "password": "supersecret1"}
    )
    assert good.status_code == 200 and good.json()["telegramId"] == tid

    bad = await api_client.post(
        "/web/auth/login", json={"email": "webacct@mail.ru", "password": "wrongpass1"}
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_web_auth_register_weak_password(api_client):
    resp = await api_client.post(
        "/web/auth/register", json={"email": "weakweb@mail.ru", "password": "short"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "weak_password"


@pytest.mark.asyncio
async def test_web_auth_login_rate_limited(api_client):
    api_client._transport.app.state.redis = _FakeRedis()
    last = None
    for _ in range(api_mod_auth_ip_limit() + 2):
        last = await api_client.post(
            "/web/auth/login",
            json={"email": "brute@mail.ru", "password": "whatever1"},
            headers={"x-client-ip": "203.0.113.77"},
        )
    assert last.status_code == 429


def api_mod_auth_ip_limit() -> int:
    from services import http_api as api_mod

    return api_mod._AUTH_IP_LIMIT


@pytest.mark.asyncio
async def test_receipts_pending_lists_only_unreceipted_completed(api_client, session_pool):
    from database.repository import Repository
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=5601)
        # completed, no receipt -> pending
        p1 = await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-p1",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_1m"),
            plan="standard_1m",
        )
        await repo.update_payment_status(p1.id, "completed")
        # completed but already receipted -> excluded
        p2 = await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-p2",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_3m"),
            plan="standard_3m",
        )
        await repo.update_payment_status(p2.id, "completed")
        await repo.set_payment_receipt(p2.id, "https://lknpd.nalog.ru/r/2")
        # still pending payment -> excluded
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-p3",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_6m"),
            plan="standard_6m",
        )

    response = await api_client.get("/web/receipts/pending")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [i["paymentId"] for i in items] == [p1.id]
    assert items[0]["amountKopecks"] == 14900
    assert items[0]["serviceName"].startswith("Оплата подписки:")


@pytest.mark.asyncio
async def test_receipts_complete_stores_and_delivers(api_client, session_pool, monkeypatch):
    from unittest.mock import AsyncMock

    from database.repository import Repository
    from services import http_api as api_mod
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=5602)
        await repo.update_user(user.id, email="buyer5602@example.com")
        payment = await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-p4",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_1m"),
            plan="standard_1m",
        )
        await repo.update_payment_status(payment.id, "completed")

    deliver = AsyncMock(return_value=True)
    deliver_email = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.moynalog, "deliver_receipt", deliver)
    monkeypatch.setattr(api_mod.moynalog, "deliver_receipt_email", deliver_email)

    url = "https://lknpd.nalog.ru/api/v1/receipt/inn/u9/print"
    response = await api_client.post(
        f"/web/receipts/{payment.id}/complete", json={"receiptUrl": url}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True and body["deliveredTelegram"] is True and body["deliveredEmail"] is True
    deliver.assert_awaited_once_with(5602, url)
    deliver_email.assert_awaited_once_with("buyer5602@example.com", url)

    async with session_pool() as session:
        stored = await Repository(session).get_payment(payment.id)
        assert stored.receipt_url == url

    # second call is idempotent — no double delivery
    response2 = await api_client.post(
        f"/web/receipts/{payment.id}/complete", json={"receiptUrl": url}
    )
    assert response2.status_code == 200
    assert response2.json().get("already") is True
    deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_receipts_complete_rejects_foreign_urls(api_client, session_pool):
    from database.repository import Repository
    from services.payment import create_invoice_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=5603)
        payment = await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-p5",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_1m"),
            plan="standard_1m",
        )
        await repo.update_payment_status(payment.id, "completed")

    response = await api_client.post(
        f"/web/receipts/{payment.id}/complete", json={"receiptUrl": "https://evil.example/r/1"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_web_trial_activate_provisions_and_returns_link(api_client, session_pool, monkeypatch):
    from unittest.mock import AsyncMock

    from database.repository import Repository
    from services import http_api as api_mod

    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=-777001)

    class _Sub:
        subscription_url = "https://144.172.101.217.sslip.io:8443/sub/trialtok"

    activate = AsyncMock(return_value=_Sub())
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)

    response = await api_client.post("/web/trial/activate", json={"telegramId": -777001})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "/sub/trialtok" in body["subscriptionUrl"]
    activate.assert_awaited_once()
    assert activate.await_args.kwargs["plan"] == "trial"


@pytest.mark.asyncio
async def test_web_trial_activate_guards(api_client, session_pool, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock

    from database.repository import Repository
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod, "activate_panel_subscription", AsyncMock())

    # unknown user -> 404
    resp = await api_client.post("/web/trial/activate", json={"telegramId": -777999})
    assert resp.status_code == 404

    # already used trial (expired) -> 409 trial_already_used
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=-777002)
        await repo.create_subscription(
            user_id=user.id, plan="trial", tier="trial",
            started_at=datetime.now(timezone.utc) - timedelta(days=10),
            expires_at=datetime.now(timezone.utc) - timedelta(days=7),
            is_active=False,
        )
    resp = await api_client.post("/web/trial/activate", json={"telegramId": -777002})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "trial_already_used"

    # active subscription -> 409 has_active_subscription
    async with session_pool() as session:
        repo = Repository(session)
        user2 = await repo.create_user(telegram_id=-777003)
        await repo.create_subscription(
            user_id=user2.id, plan="standard_1m", tier="standard",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )
    resp = await api_client.post("/web/trial/activate", json={"telegramId": -777003})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "has_active_subscription"
