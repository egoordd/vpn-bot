import smtplib

import pytest

from services import mailer


@pytest.fixture
def smtp_settings(monkeypatch):
    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(mailer.settings, "SMTP_PORT", 465)
    monkeypatch.setattr(mailer.settings, "SMTP_USER", "sender@example.com")
    monkeypatch.setattr(
        mailer.settings, "SMTP_PASSWORD", type(mailer.settings.SMTP_PASSWORD)("app-pass")
    )
    monkeypatch.setattr(mailer.settings, "SMTP_FROM", "UnLock VPN <sender@example.com>")


class _FakeSMTP:
    """Stands in for smtplib.SMTP/SMTP_SSL; records the calls made on it."""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent = []
        self.starttls_called = False
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.starttls_called = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeSMTP.instances = []


@pytest.mark.unit
def test_is_configured_requires_host_and_from(monkeypatch):
    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "")
    monkeypatch.setattr(mailer.settings, "SMTP_FROM", "a@b.c")
    assert mailer.is_configured() is False
    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(mailer.settings, "SMTP_FROM", "")
    assert mailer.is_configured() is False
    monkeypatch.setattr(mailer.settings, "SMTP_FROM", "a@b.c")
    assert mailer.is_configured() is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_returns_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "")
    assert await mailer.send_email("to@example.com", "s", "t") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_ssl_port_uses_implicit_tls(smtp_settings, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)

    ok = await mailer.send_email(
        "buyer@example.com", "Чек по оплате", "текст", html="<p>чек</p>"
    )

    assert ok is True
    (client,) = _FakeSMTP.instances
    assert (client.host, client.port) == ("smtp.example.com", 465)
    assert client.starttls_called is False
    assert client.logged_in == ("sender@example.com", "app-pass")
    (message,) = client.sent
    assert message["To"] == "buyer@example.com"
    assert message["From"] == "UnLock VPN <sender@example.com>"
    assert message["Subject"] == "Чек по оплате"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_other_port_uses_starttls(smtp_settings, monkeypatch):
    monkeypatch.setattr(mailer.settings, "SMTP_PORT", 587)
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    ok = await mailer.send_email("buyer@example.com", "s", "t")

    assert ok is True
    (client,) = _FakeSMTP.instances
    assert client.port == 587
    assert client.starttls_called is True
    assert len(client.sent) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_failure_is_swallowed(smtp_settings, monkeypatch):
    def _boom(*args, **kwargs):
        raise smtplib.SMTPException("relay refused")

    monkeypatch.setattr(smtplib, "SMTP_SSL", _boom)

    assert await mailer.send_email("buyer@example.com", "s", "t") is False
