import pytest
from aioresponses import aioresponses

from services import moynalog


@pytest.fixture(autouse=True)
def _reset_token(monkeypatch):
    # The module caches the access token in-process; clear it between tests.
    monkeypatch.setattr(moynalog, "_token", None)
    monkeypatch.setattr(moynalog, "_token_expires_at", 0.0)


@pytest.fixture
def mn_settings(monkeypatch):
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_API_URL", "https://lknpd.nalog.ru/api/v1")
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_INN", "220454839571")
    monkeypatch.setattr(
        moynalog.settings, "MOYNALOG_PASSWORD", type(moynalog.settings.MOYNALOG_PASSWORD)("secret")
    )
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_SERVICE_NAME", "Оплата подписки UnLock VPN")


@pytest.mark.unit
def test_is_configured_requires_inn_and_password(monkeypatch):
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_INN", "")
    assert moynalog.is_configured() is False


@pytest.mark.unit
def test_receipt_url_format(mn_settings):
    assert (
        moynalog.receipt_url("abc-123")
        == "https://lknpd.nalog.ru/api/v1/receipt/220454839571/abc-123/print"
    )


@pytest.mark.unit
async def test_create_income_authenticates_and_returns_url(mn_settings):
    with aioresponses() as mocked:
        mocked.post("https://lknpd.nalog.ru/api/v1/auth/lkfl", payload={"token": "tok-1", "refreshToken": "r"})
        mocked.post("https://lknpd.nalog.ru/api/v1/income", payload={"approvedReceiptUuid": "rcpt-9"})

        url = await moynalog.create_income(14900, name="Оплата подписки: Обычный")

    assert url == "https://lknpd.nalog.ru/api/v1/receipt/220454839571/rcpt-9/print"


@pytest.mark.unit
async def test_create_income_sends_full_amount_in_rub(mn_settings):
    captured = {}

    with aioresponses() as mocked:
        mocked.post("https://lknpd.nalog.ru/api/v1/auth/lkfl", payload={"token": "tok-1"})

        def _cb(url, **kwargs):
            captured["json"] = kwargs.get("json") or {}
            from aioresponses.core import CallbackResult

            return CallbackResult(status=200, payload={"approvedReceiptUuid": "u1"})

        mocked.post("https://lknpd.nalog.ru/api/v1/income", callback=_cb)
        await moynalog.create_income(14900, name="Подписка")

    assert captured["json"]["services"][0]["amount"] == 149.0
    assert captured["json"]["totalAmount"] == "149.0"
    assert captured["json"]["services"][0]["name"] == "Подписка"
    assert captured["json"]["client"]["incomeType"] == "FROM_INDIVIDUAL"


@pytest.mark.unit
async def test_issue_receipt_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_INN", "")
    assert await moynalog.issue_receipt(14900) is None


@pytest.mark.unit
async def test_issue_receipt_swallows_errors(mn_settings):
    with aioresponses() as mocked:
        mocked.post("https://lknpd.nalog.ru/api/v1/auth/lkfl", status=500, payload={"e": 1})
        # best-effort: must not raise, returns None
        assert await moynalog.issue_receipt(14900) is None
