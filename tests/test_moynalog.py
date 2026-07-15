import pytest
from aioresponses import aioresponses

from services import moynalog


@pytest.fixture(autouse=True)
def _reset_token(monkeypatch):
    # The module caches the access/refresh token in-process; clear between tests.
    monkeypatch.setattr(moynalog, "_token", None)
    monkeypatch.setattr(moynalog, "_token_expires_at", 0.0)
    monkeypatch.setattr(moynalog, "_refresh_token", None)


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
def test_is_configured_accepts_refresh_token_without_password(monkeypatch):
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_INN", "220454839571")
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_PASSWORD", type(moynalog.settings.MOYNALOG_PASSWORD)(""))
    monkeypatch.setattr(
        moynalog.settings, "MOYNALOG_REFRESH_TOKEN", type(moynalog.settings.MOYNALOG_REFRESH_TOKEN)("rt-1")
    )
    assert moynalog.is_configured() is True


@pytest.mark.unit
async def test_auth_uses_refresh_token_endpoint_when_set(mn_settings, monkeypatch):
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_PASSWORD", type(moynalog.settings.MOYNALOG_PASSWORD)(""))
    monkeypatch.setattr(
        moynalog.settings, "MOYNALOG_REFRESH_TOKEN", type(moynalog.settings.MOYNALOG_REFRESH_TOKEN)("rt-1")
    )
    monkeypatch.setattr(moynalog.settings, "MOYNALOG_DEVICE_ID", "dev-123")
    captured = {}

    with aioresponses() as mocked:
        def _auth_cb(url, **kwargs):
            captured["json"] = kwargs.get("json") or {}
            from aioresponses.core import CallbackResult

            return CallbackResult(status=200, payload={"token": "acc-1", "refreshToken": "rt-2"})

        mocked.post("https://lknpd.nalog.ru/api/v1/auth/token", callback=_auth_cb)
        mocked.post("https://lknpd.nalog.ru/api/v1/income", payload={"approvedReceiptUuid": "u9"})

        url = await moynalog.create_income(14900)

    assert captured["json"]["refreshToken"] == "rt-1"
    assert captured["json"]["deviceInfo"]["sourceDeviceId"] == "dev-123"
    assert url.endswith("/receipt/220454839571/u9/print")


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


@pytest.mark.unit
async def test_deliver_receipt_email_sends_link_via_mailer(monkeypatch):
    from unittest.mock import AsyncMock

    from services import mailer

    send = AsyncMock(return_value=True)
    monkeypatch.setattr(mailer, "send_email", send)

    url = "https://lknpd.nalog.ru/api/v1/receipt/220454839571/u1/print"
    assert await moynalog.deliver_receipt_email("buyer@example.com", url) is True

    send.assert_awaited_once()
    to, subject, text = send.await_args.args
    assert to == "buyer@example.com"
    assert "Чек" in subject
    assert url in text
    assert url in send.await_args.kwargs["html"]


@pytest.mark.unit
async def test_deliver_receipt_email_skips_empty_recipient(monkeypatch):
    from unittest.mock import AsyncMock

    from services import mailer

    send = AsyncMock(return_value=True)
    monkeypatch.setattr(mailer, "send_email", send)

    assert await moynalog.deliver_receipt_email("", "https://x/receipt") is False
    send.assert_not_awaited()
