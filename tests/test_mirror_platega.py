"""Platega payments in the mirror: a paid invoice turns into time exactly once."""

from datetime import datetime, timedelta, timezone

import pytest

from database.models import Payment
from database.repository import Repository
from services import mirror_platega


class FakePlatega:
    """Stands in for Platega's API: records calls, answers from a script."""

    def __init__(self, *, status: str = "PENDING", amount: float | None = None, fail_create=False):
        self.status_value = status
        self.amount_value = amount
        self.fail_create = fail_create
        self.created: list[dict] = []
        self.status_calls = 0

    async def create(self, *, amount_rub, method, description, payload, user_id):
        if self.fail_create:
            raise mirror_platega.PlategaError("HTTP 400")
        self.created.append(
            {"amount": amount_rub, "method": method, "description": description,
             "payload": payload, "user_id": user_id}
        )
        return "tx-" + str(len(self.created)), "https://pay.platega.io/tx"

    async def status(self, transaction_id):
        self.status_calls += 1
        return self.status_value, self.amount_value


class FakeActivation:
    def __init__(self, *, fail_times: int = 0):
        self.calls = 0
        self.fail_times = fail_times

    async def __call__(self, session, user_id, plan):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("panel unreachable")
        now = datetime.now(timezone.utc)
        return await Repository(session).create_subscription(
            user_id=user_id,
            plan=plan,
            started_at=now,
            expires_at=now + timedelta(days=30),
            panel_username=f"tg_{user_id}",
            subscription_url="https://example.invalid/sub/token",
        )


async def _buyer(session, telegram_id=5001):
    return await Repository(session).get_or_create_user(telegram_id, "buyer")


async def _open_invoice(session, client, plan="standard_1m", method=2):
    user = await _buyer(session)
    payment, url = await mirror_platega.start_payment(
        session, client, user=user, plan=plan, method=method
    )
    return payment, url


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(mirror_platega, "MERCHANT_ID", "merchant-uuid")
    monkeypatch.setattr(mirror_platega, "SECRET", "secret-key")
    monkeypatch.setattr(mirror_platega, "ENABLED_METHODS", (2, 11))


def test_needs_merchant_secret_and_a_method(monkeypatch):
    assert mirror_platega.is_configured()
    monkeypatch.setattr(mirror_platega, "SECRET", "")
    assert not mirror_platega.is_configured()


def test_payload_carries_the_plan():
    payload = mirror_platega.make_payload(user_id=7, plan="standard_3m")
    assert mirror_platega.plan_from_payload(payload) == "standard_3m"
    assert mirror_platega.plan_from_payload("unlock:7:standard_3m:x") is None


@pytest.mark.asyncio
async def test_an_invoice_is_recorded_before_the_buyer_pays(db_session):
    client = FakePlatega()
    payment, url = await _open_invoice(db_session, client, plan="standard_3m", method=11)

    assert url == "https://pay.platega.io/tx"
    assert payment.provider == "platega"
    assert payment.status == "pending"
    assert payment.currency == "RUB"
    assert payment.amount == 399 * 100
    assert payment.external_invoice_id == "tx-1"
    sent = client.created[0]
    assert (sent["amount"], sent["method"]) == (399, 11)
    assert sent["payload"] == payment.invoice_payload


@pytest.mark.asyncio
async def test_a_refused_invoice_is_closed_not_left_hanging(db_session):
    with pytest.raises(mirror_platega.PlategaError):
        await _open_invoice(db_session, FakePlatega(fail_create=True))

    payments = (await db_session.execute(Payment.__table__.select())).all()
    assert [row.status for row in payments] == ["failed"]


@pytest.mark.asyncio
async def test_a_confirmed_payment_grants_the_subscription_once(db_session):
    client = FakePlatega()
    payment, _ = await _open_invoice(db_session, client)
    client.status_value, client.amount_value = "CONFIRMED", 149.0
    activate = FakeActivation()

    first = await mirror_platega.settle(db_session, client, payment.id, activate=activate)
    second = await mirror_platega.settle(db_session, client, payment.id, activate=activate)

    assert first.state == "completed"
    assert first.subscription is not None
    assert second.state == "already"
    assert activate.calls == 1
    refreshed = await Repository(db_session).get_payment(payment.id)
    assert refreshed.status == "completed"


@pytest.mark.asyncio
async def test_an_unpaid_invoice_stays_open(db_session):
    client = FakePlatega(status="PENDING")
    payment, _ = await _open_invoice(db_session, client)
    activate = FakeActivation()

    result = await mirror_platega.settle(db_session, client, payment.id, activate=activate)

    assert result.state == "pending"
    assert activate.calls == 0


@pytest.mark.asyncio
async def test_a_canceled_invoice_is_closed_without_time(db_session):
    client = FakePlatega()
    payment, _ = await _open_invoice(db_session, client)
    client.status_value = "CANCELED"
    activate = FakeActivation()

    result = await mirror_platega.settle(db_session, client, payment.id, activate=activate)

    assert result.state == "canceled"
    assert activate.calls == 0
    assert (await Repository(db_session).get_payment(payment.id)).status == "canceled"


@pytest.mark.asyncio
async def test_a_short_payment_is_never_granted(db_session):
    """The amount comes back from Platega; it must match what we asked for."""
    client = FakePlatega()
    payment, _ = await _open_invoice(db_session, client)
    client.status_value, client.amount_value = "CONFIRMED", 1.0
    activate = FakeActivation()

    result = await mirror_platega.settle(db_session, client, payment.id, activate=activate)

    assert result.state == "mismatch"
    assert activate.calls == 0


@pytest.mark.asyncio
async def test_a_paid_invoice_survives_a_panel_outage(db_session):
    """Money taken, panel down: the payment stays owed and is granted later."""
    client = FakePlatega()
    payment, _ = await _open_invoice(db_session, client)
    client.status_value, client.amount_value = "CONFIRMED", 149.0
    activate = FakeActivation(fail_times=1)

    first = await mirror_platega.settle(db_session, client, payment.id, activate=activate)
    assert first.state == "failed"
    assert (await Repository(db_session).get_payment(payment.id)).status == "confirmed"

    second = await mirror_platega.settle(db_session, client, payment.id, activate=activate)
    assert second.state == "completed"
    assert activate.calls == 2


@pytest.mark.asyncio
async def test_the_watcher_sees_only_open_platega_invoices(db_session):
    client = FakePlatega()
    mine, _ = await _open_invoice(db_session, client)
    user = await _buyer(db_session)
    other = Payment(
        user_id=user.id, amount=14900, currency="RUB", provider="yookassa",
        invoice_payload="unlock:x", status="pending",
    )
    db_session.add(other)
    await db_session.commit()

    ids = [p.id for p in await mirror_platega.open_payments(db_session)]

    assert ids == [mine.id]


def test_payment_screens_name_price_and_method():
    text = mirror_platega.invoice_text("standard_6m", 2)
    assert "699" in text
    assert "СБП" in text


# --- the mirror's screens ---------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from services import mirror_bot  # noqa: E402


def _buttons(markup):
    return [button for row in markup["inline_keyboard"] for button in row]


def test_tariffs_offer_a_buy_button_per_paid_plan():
    callbacks = [b.get("callback_data") for b in _buttons(mirror_bot.tariffs_keyboard())]

    assert callbacks[:4] == [f"pl_plan:{plan}" for plan in mirror_platega.PAID_PLANS]


def test_without_platega_the_tariffs_screen_sells_nothing(monkeypatch):
    monkeypatch.setattr(mirror_platega, "SECRET", "")

    callbacks = [b.get("callback_data") for b in _buttons(mirror_bot.tariffs_keyboard())]

    assert not any((c or "").startswith("pl_") for c in callbacks)


def test_payment_screens_pass_the_reviewers_vocabulary_check():
    from tests.test_mirror_bot import RESTRICTED_VOCABULARY

    screens = {
        "checkout": mirror_platega.checkout_text("standard_1m"),
        "invoice": mirror_platega.invoice_text("standard_1m", 11),
        "paid": mirror_platega.paid_text(SimpleNamespace(plan="standard_1m"), "11.10.2026"),
        "pending": mirror_platega.PENDING_ANSWER,
        "canceled": mirror_platega.CANCELED_ANSWER,
        "problem": mirror_platega.PROBLEM_ANSWER,
        "buttons": " ".join(b["text"] for b in _buttons(mirror_bot.tariffs_keyboard())),
        "methods": " ".join(mirror_platega.METHOD_LABELS.values()),
    }
    offenders = {
        f"{name}:{word}" for name, body in screens.items() for word in RESTRICTED_VOCABULARY
        if word in body.lower()
    }
    assert not offenders


class FakeTelegram:
    def __init__(self):
        self.calls = []

    async def call(self, method, payload=None):
        self.calls.append((method, payload or {}))
        return {}


@pytest.mark.asyncio
async def test_choosing_a_method_hands_the_buyer_plategas_pay_page(session_pool, monkeypatch):
    telegram = FakeTelegram()
    bot = mirror_bot.MirrorBot(telegram, session_pool)
    bot.platega = FakePlatega()

    await bot.handle_callback(
        {
            "id": "cb1",
            "from": {"id": 5002, "username": "buyer"},
            "message": {"chat": {"id": 5002}, "message_id": 10},
            "data": "pl_pay:standard_1m:2",
        }
    )

    screen = next(p for m, p in telegram.calls if m in {"editMessageText", "sendMessage"})
    urls = [b.get("url") for b in _buttons(screen["reply_markup"])]
    callbacks = [b.get("callback_data") or "" for b in _buttons(screen["reply_markup"])]
    assert "https://pay.platega.io/tx" in urls
    assert any(c.startswith("pl_check:") for c in callbacks)


@pytest.mark.asyncio
async def test_nobody_can_check_someone_elses_payment(session_pool):
    telegram = FakeTelegram()
    bot = mirror_bot.MirrorBot(telegram, session_pool)
    bot.platega = FakePlatega()
    async with session_pool() as session:
        payment, _ = await _open_invoice(session, bot.platega)

    await bot.handle_callback(
        {
            "id": "cb2",
            "from": {"id": 9999, "username": "stranger"},
            "message": {"chat": {"id": 9999}, "message_id": 11},
            "data": f"pl_check:{payment.id}",
        }
    )

    answer = next(p for m, p in telegram.calls if m == "answerCallbackQuery")
    assert "не найден" in answer.get("text", "")
    assert bot.platega.status_calls == 0
