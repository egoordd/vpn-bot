import re

import pytest
from aioresponses import aioresponses

from services import cryptobot
from services.cryptobot import CryptoBotError


@pytest.fixture
def cryptobot_settings(monkeypatch):
    monkeypatch.setattr(cryptobot.settings, "CRYPTOBOT_API_URL", "https://pay.crypt.bot/api")
    monkeypatch.setattr(cryptobot.settings, "CRYPTOBOT_TOKEN", "token")


@pytest.mark.unit
async def test_request_raises_when_token_empty(cryptobot_settings, monkeypatch):
    monkeypatch.setattr(cryptobot.settings, "CRYPTOBOT_TOKEN", "")

    with pytest.raises(CryptoBotError):
        await cryptobot._request("GET", "getInvoices")


@pytest.mark.unit
async def test_create_invoice_success(cryptobot_settings):
    with aioresponses() as mocked:
        mocked.post(
            "https://pay.crypt.bot/api/createInvoice",
            payload={"ok": True, "result": {"invoice_id": 1, "pay_url": "https://pay.example"}},
        )

        result = await cryptobot.create_invoice("1.99", "payload", "description")

    assert result == {"invoice_id": 1, "pay_url": "https://pay.example"}


@pytest.mark.unit
async def test_create_invoice_api_error(cryptobot_settings):
    with aioresponses() as mocked:
        mocked.post(
            "https://pay.crypt.bot/api/createInvoice",
            payload={"ok": False, "error": "bad request"},
        )

        with pytest.raises(CryptoBotError):
            await cryptobot.create_invoice("1.99", "payload", "description")


@pytest.mark.unit
async def test_create_invoice_http_error(cryptobot_settings):
    with aioresponses() as mocked:
        mocked.post(
            "https://pay.crypt.bot/api/createInvoice",
            status=500,
            payload={"ok": False, "error": "server"},
        )

        with pytest.raises(CryptoBotError):
            await cryptobot.create_invoice("1.99", "payload", "description")


@pytest.mark.unit
async def test_get_invoices_by_status_filters_dict_items(cryptobot_settings):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"^https://pay\.crypt\.bot/api/getInvoices"),
            payload={"ok": True, "result": {"items": [{"invoice_id": 1}, "bad", {"invoice_id": 2}]}},
        )

        assert await cryptobot.get_invoices_by_status("paid") == [{"invoice_id": 1}, {"invoice_id": 2}]


@pytest.mark.unit
async def test_get_invoice_by_id_returns_first_or_none(cryptobot_settings):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"^https://pay\.crypt\.bot/api/getInvoices"),
            payload={"ok": True, "result": {"items": [{"invoice_id": 1}, {"invoice_id": 2}]}},
        )
        assert await cryptobot.get_invoice_by_id(1) == {"invoice_id": 1}

    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"^https://pay\.crypt\.bot/api/getInvoices"),
            payload={"ok": True, "result": {"items": []}},
        )
        assert await cryptobot.get_invoice_by_id(1) is None


@pytest.mark.unit
async def test_create_invoice_rejects_unexpected_result(cryptobot_settings):
    with aioresponses() as mocked:
        mocked.post(
            "https://pay.crypt.bot/api/createInvoice",
            payload={"ok": True, "result": ["unexpected"]},
        )

        with pytest.raises(CryptoBotError):
            await cryptobot.create_invoice("1.99", "payload", "description")


@pytest.mark.unit
async def test_upstream_500_raises_unavailable(cryptobot_settings):
    from services.cryptobot import CryptoBotUnavailableError

    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"https://pay\.crypt\.bot/api/getInvoices.*"),
            status=500,
            body="<html>Bad Gateway</html>",
            content_type="text/html",
        )
        with pytest.raises(CryptoBotUnavailableError):
            await cryptobot.get_invoices_by_status("paid")


@pytest.mark.unit
async def test_non_json_error_page_is_unavailable_not_generic(cryptobot_settings):
    from services.cryptobot import CryptoBotUnavailableError

    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"https://pay\.crypt\.bot/api/getInvoices.*"),
            status=502,
            body="upstream down",
            content_type="text/html",
        )
        with pytest.raises(CryptoBotUnavailableError):
            await cryptobot.get_invoices_by_status("paid")


@pytest.mark.unit
async def test_unavailable_is_a_cryptobot_error_subclass():
    from services.cryptobot import CryptoBotUnavailableError

    assert issubclass(CryptoBotUnavailableError, CryptoBotError)


@pytest.mark.unit
def test_an_invoice_outlives_a_slow_transfer():
    """An hour is the wrong scale for this payment method. Paying from a
    CryptoBot balance is instant, but a transfer from an outside wallet has to
    confirm on-chain first. A customer said on 2026-08-25 that he had paid
    "within the hour" and found nothing credited; his invoice had lapsed unpaid,
    and no invoice on the account had ever been paid — five attempts, none
    completed."""
    assert cryptobot.CRYPTO_INVOICE_TTL >= 6 * 3600


@pytest.mark.unit
def test_the_lifetime_is_what_new_invoices_get():
    """The constant is worthless if the default argument still says 3600."""
    import inspect

    default = inspect.signature(cryptobot.create_invoice).parameters["expires_in"].default
    assert default == cryptobot.CRYPTO_INVOICE_TTL
