import pytest
from aioresponses import aioresponses

from services import yookassa
from services.yookassa import YooKassaError


@pytest.fixture
def yk_settings(monkeypatch):
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_API_URL", "https://api.yookassa.ru/v3")
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_SHOP_ID", "shop-1")
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_SECRET_KEY", type(yookassa.settings.YOOKASSA_SECRET_KEY)("secret-1"))
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_RETURN_URL", "https://t.me/unlkvpn_bot")
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_RECEIPT_ENABLED", False)


@pytest.mark.unit
def test_is_configured_requires_both_keys(monkeypatch):
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_SHOP_ID", "")
    assert yookassa.is_configured() is False
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_SHOP_ID", "shop")
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_SECRET_KEY", type(yookassa.settings.YOOKASSA_SECRET_KEY)(""))
    assert yookassa.is_configured() is False


@pytest.mark.unit
def test_rub_value_formats_kopecks():
    assert yookassa.rub_value(14900) == "149.00"
    assert yookassa.rub_value(9900) == "99.00"


@pytest.mark.unit
def test_confirmation_url_extracts_redirect():
    payment = {"confirmation": {"type": "redirect", "confirmation_url": "https://yoomoney.ru/pay/abc"}}
    assert yookassa.confirmation_url(payment) == "https://yoomoney.ru/pay/abc"
    assert yookassa.confirmation_url({"confirmation": {}}) is None
    assert yookassa.confirmation_url({}) is None


@pytest.mark.unit
async def test_create_payment_success(yk_settings):
    with aioresponses() as mocked:
        mocked.post(
            "https://api.yookassa.ru/v3/payments",
            payload={
                "id": "2c85a...",
                "status": "pending",
                "confirmation": {"type": "redirect", "confirmation_url": "https://yoomoney.ru/pay/xyz"},
            },
        )
        result = await yookassa.create_payment(
            amount_kopecks=14900,
            description="Standard 1m",
            metadata={"user_id": 7, "plan": "standard_1m"},
        )

    assert result["id"] == "2c85a..."
    assert yookassa.confirmation_url(result) == "https://yoomoney.ru/pay/xyz"


@pytest.mark.unit
async def test_create_payment_sends_auth_and_idempotence(yk_settings):
    captured = {}

    with aioresponses() as mocked:
        def _cb(url, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}
            captured["json"] = kwargs.get("json") or {}
            from aioresponses.core import CallbackResult

            return CallbackResult(
                status=200,
                payload={"id": "p1", "confirmation": {"confirmation_url": "https://y/x"}},
            )

        mocked.post("https://api.yookassa.ru/v3/payments", callback=_cb)
        await yookassa.create_payment(
            amount_kopecks=14900, description="d", metadata={"user_id": 1, "plan": "standard_1m"}
        )

    assert captured["headers"]["Authorization"].startswith("Basic ")
    assert captured["headers"].get("Idempotence-Key")
    assert captured["json"]["amount"] == {"value": "149.00", "currency": "RUB"}
    assert captured["json"]["capture"] is True
    assert captured["json"]["confirmation"]["type"] == "redirect"


@pytest.mark.unit
async def test_create_payment_attaches_receipt_when_enabled(yk_settings, monkeypatch):
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_RECEIPT_ENABLED", True)
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_RECEIPT_EMAIL", "buyer@example.com")
    captured = {}

    with aioresponses() as mocked:
        def _cb(url, **kwargs):
            captured["json"] = kwargs.get("json") or {}
            from aioresponses.core import CallbackResult

            return CallbackResult(status=200, payload={"id": "p1", "confirmation": {"confirmation_url": "https://y/x"}})

        mocked.post("https://api.yookassa.ru/v3/payments", callback=_cb)
        await yookassa.create_payment(
            amount_kopecks=14900, description="Standard", metadata={"user_id": 1, "plan": "standard_1m"}
        )

    receipt = captured["json"]["receipt"]
    assert receipt["customer"]["email"] == "buyer@example.com"
    assert receipt["items"][0]["amount"]["value"] == "149.00"
    assert receipt["items"][0]["vat_code"] == 1


@pytest.mark.unit
async def test_receipt_on_page_mode_omits_customer(yk_settings, monkeypatch):
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_RECEIPT_ENABLED", True)
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_COLLECT_EMAIL_ON_PAGE", True)
    captured = {}

    with aioresponses() as mocked:
        def _cb(url, **kwargs):
            captured["json"] = kwargs.get("json") or {}
            from aioresponses.core import CallbackResult

            return CallbackResult(status=200, payload={"id": "p1", "confirmation": {"confirmation_url": "https://y/x"}})

        mocked.post("https://api.yookassa.ru/v3/payments", callback=_cb)
        await yookassa.create_payment(
            amount_kopecks=14900, description="Standard", metadata={"user_id": 1, "plan": "standard_1m"}
        )

    receipt = captured["json"]["receipt"]
    assert "customer" not in receipt  # YooKassa collects the email on its page
    assert receipt["items"][0]["amount"]["value"] == "149.00"


@pytest.mark.unit
async def test_create_payment_http_error_raises(yk_settings):
    with aioresponses() as mocked:
        mocked.post("https://api.yookassa.ru/v3/payments", status=401, payload={"type": "error"})
        with pytest.raises(YooKassaError):
            await yookassa.create_payment(
                amount_kopecks=14900, description="d", metadata={"user_id": 1, "plan": "standard_1m"}
            )


@pytest.mark.unit
async def test_request_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_SHOP_ID", "")
    monkeypatch.setattr(yookassa.settings, "YOOKASSA_SECRET_KEY", type(yookassa.settings.YOOKASSA_SECRET_KEY)(""))
    with pytest.raises(YooKassaError):
        await yookassa.get_payment("p1")


@pytest.mark.unit
async def test_get_payment_returns_status(yk_settings):
    with aioresponses() as mocked:
        mocked.get(
            "https://api.yookassa.ru/v3/payments/p1",
            payload={"id": "p1", "status": "succeeded", "amount": {"value": "149.00", "currency": "RUB"}},
        )
        payment = await yookassa.get_payment("p1")

    assert payment["status"] == "succeeded"
