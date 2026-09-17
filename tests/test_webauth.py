import pytest

from services import webauth
from services.billing_api import (
    WebAuthError,
    authenticate_web_account,
    register_web_account,
)
from database.repository import Repository


def test_hash_verify_roundtrip():
    stored = webauth.hash_password("correct horse battery")
    assert stored.startswith("pbkdf2_sha256$")
    assert webauth.verify_password("correct horse battery", stored) is True
    assert webauth.verify_password("wrong", stored) is False


def test_verify_rejects_blank_and_tampered():
    assert webauth.verify_password("x", None) is False
    assert webauth.verify_password("x", "") is False
    assert webauth.verify_password("x", "not$a$valid$hash") is False


def test_password_acceptance_bounds():
    assert webauth.is_password_acceptable("1234567") is False
    assert webauth.is_password_acceptable("12345678") is True
    assert webauth.is_password_acceptable("a" * 201) is False


@pytest.mark.integration
async def test_register_creates_account_and_login(session_pool):
    async with session_pool() as session:
        tid = await register_web_account(session, email="New@Mail.RU", password="supersecret1")
        assert tid < 0  # email account = synthetic negative id
        user = await Repository(session).get_user_by_email("new@mail.ru")
        assert user is not None and user.web_password_hash

    async with session_pool() as session:
        ok = await authenticate_web_account(session, email="new@mail.ru", password="supersecret1")
        assert ok == tid
        bad = await authenticate_web_account(session, email="new@mail.ru", password="nope")
        assert bad is None


@pytest.mark.integration
async def test_register_does_not_claim_existing_guest_email_account(session_pool):
    # A guest's email is not proof of ownership. Recovery needs a separately
    # verified process and public registration must leave purchases untouched.
    async with session_pool() as session:
        repo = Repository(session)
        guest = await repo.create_user(telegram_id=-555001)
        await repo.update_user(guest.id, email="guest@mail.ru")
        await repo.create_yookassa_payment(guest.id, 14900, "yk-guest-paid", "unlock:guest", "standard_1m")
        await repo.complete_payment_by_external_id("yk-guest-paid")

    async with session_pool() as session:
        with pytest.raises(WebAuthError) as exc:
            await register_web_account(session, email="guest@mail.ru", password="supersecret1")
        assert exc.value.code == "already_registered"

    async with session_pool() as session:
        guest = await Repository(session).get_user_by_email("guest@mail.ru")
        assert guest.telegram_id == -555001
        assert guest.web_password_hash is None
        assert await authenticate_web_account(session, email="guest@mail.ru", password="supersecret1") is None


async def _walked_away_guest(session_pool, email: str, *, payment_status: str | None) -> int:
    """A guest a checkout left behind: email, no password, nothing bought."""
    async with session_pool() as session:
        repo = Repository(session)
        guest = await repo.create_user(telegram_id=-555100 - len(email))
        await repo.update_user(guest.id, email=email)
        if payment_status is not None:
            payment = await repo.create_yookassa_payment(
                guest.id, 39900, f"yk-{email}", "unlock:guest", "standard_3m"
            )
            if payment_status != "pending":
                await repo.update_payment_status(payment.id, payment_status)
        return guest.telegram_id


def _yookassa_says(monkeypatch, status: str | Exception):
    from services import yookassa

    async def get_payment(payment_id: str):
        if isinstance(status, Exception):
            raise status
        return {"id": payment_id, "status": status}

    monkeypatch.setattr(yookassa, "get_payment", get_payment)


@pytest.mark.integration
@pytest.mark.parametrize("payment_status", [None, "canceled"])
async def test_register_takes_over_account_an_unpaid_checkout_left(session_pool, payment_status):
    email = f"left-{payment_status}@mail.ru"
    guest_id = await _walked_away_guest(session_pool, email, payment_status=payment_status)

    async with session_pool() as session:
        tid = await register_web_account(session, email=email.upper(), password="supersecret1")
    assert tid == guest_id

    async with session_pool() as session:
        assert await authenticate_web_account(session, email=email, password="supersecret1") == guest_id
        assert len(await Repository(session).list_users()) == 1


@pytest.mark.integration
async def test_register_closes_checkout_yookassa_already_canceled(session_pool, monkeypatch):
    guest_id = await _walked_away_guest(session_pool, "expired@mail.ru", payment_status="pending")
    _yookassa_says(monkeypatch, "canceled")

    async with session_pool() as session:
        assert await register_web_account(session, email="expired@mail.ru", password="supersecret1") == guest_id

    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("yk-expired@mail.ru")
        assert payment.status == "canceled"


@pytest.mark.integration
@pytest.mark.parametrize(
    "remote", ["pending", "waiting_for_capture", "succeeded", RuntimeError("yookassa down")]
)
async def test_register_waits_while_checkout_may_still_pay(session_pool, monkeypatch, remote):
    # The money may still arrive. Whoever sets a password now would own the
    # subscription it buys, and knowing the address proves nothing.
    email = "paying-now@mail.ru"
    await _walked_away_guest(session_pool, email, payment_status="pending")
    _yookassa_says(monkeypatch, remote)

    async with session_pool() as session:
        with pytest.raises(WebAuthError) as exc:
            await register_web_account(session, email=email, password="supersecret1")
        assert exc.value.code == "payment_in_progress"

    async with session_pool() as session:
        guest = await Repository(session).get_user_by_email(email)
        assert guest.web_password_hash is None
        payment = await Repository(session).get_payment_by_external_id(f"yk-{email}")
        assert payment.status == "pending"


@pytest.mark.integration
async def test_register_rejects_duplicate(session_pool):
    async with session_pool() as session:
        await register_web_account(session, email="dup@mail.ru", password="supersecret1")
    async with session_pool() as session:
        with pytest.raises(WebAuthError) as exc:
            await register_web_account(session, email="dup@mail.ru", password="another12")
        assert exc.value.code == "already_registered"


@pytest.mark.integration
async def test_register_rejects_weak_password(session_pool):
    async with session_pool() as session:
        with pytest.raises(WebAuthError) as exc:
            await register_web_account(session, email="weak@mail.ru", password="short")
        assert exc.value.code == "weak_password"
