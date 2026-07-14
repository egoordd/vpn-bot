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
async def test_register_claims_existing_guest_email_account(session_pool):
    # A prior email purchase created a passwordless account; registering claims it.
    async with session_pool() as session:
        repo = Repository(session)
        guest = await repo.create_user(telegram_id=-555001)
        await repo.update_user(guest.id, email="guest@mail.ru")

    async with session_pool() as session:
        tid = await register_web_account(session, email="guest@mail.ru", password="supersecret1")
        assert tid == -555001  # same account, now with a password

    async with session_pool() as session:
        assert await authenticate_web_account(session, email="guest@mail.ru", password="supersecret1") == -555001


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
