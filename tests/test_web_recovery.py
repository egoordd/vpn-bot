"""Verified recovery: a subscription link buys a password, once."""

import base64
from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services import billing_api, webauth


def _token(panel_username: str) -> str:
    head = base64.urlsafe_b64encode(f"{panel_username},1700000000".encode()).decode().rstrip("=")
    return head + "Zm9vYmFy"


def _link(panel_username: str, flavor: str = "") -> str:
    suffix = f"/{flavor}" if flavor else ""
    return f"https://sub.unlockvpn.site/sub/{_token(panel_username)}{suffix}"


async def _guest_with_subscription(session, panel_username: str, telegram_id: int, email=None):
    repo = Repository(session)
    user = await repo.get_or_create_user(telegram_id)
    if email:
        await repo.update_user(user.id, email=email)
    now = datetime.now(timezone.utc)
    await repo.create_subscription(
        user_id=user.id,
        plan="standard_1m",
        started_at=now,
        expires_at=now + timedelta(days=30),
        panel_username=panel_username,
        sub_token=panel_username,
        subscription_url=_link(panel_username),
    )
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_link_lets_a_passwordless_guest_set_a_password(db_session) -> None:
    user = await _guest_with_subscription(db_session, "tg_-901", -901, email="guest@mail.ru")

    telegram_id = await billing_api.set_web_password_by_subscription(
        db_session, subscription_link=_link("tg_-901"), password="correct horse battery"
    )

    assert telegram_id == user.telegram_id
    signed_in = await billing_api.authenticate_web_account(
        db_session, email="guest@mail.ru", password="correct horse battery"
    )
    assert signed_in == user.telegram_id


@pytest.mark.asyncio
async def test_link_with_a_flavor_suffix_is_accepted(db_session) -> None:
    user = await _guest_with_subscription(db_session, "tg_-902", -902)

    telegram_id = await billing_api.set_web_password_by_subscription(
        db_session,
        subscription_link=_link("tg_-902", "split"),
        password="correct horse battery",
    )

    assert telegram_id == user.telegram_id


@pytest.mark.asyncio
async def test_email_is_attached_when_the_account_has_none(db_session) -> None:
    user = await _guest_with_subscription(db_session, "tg_-903", -903)

    await billing_api.set_web_password_by_subscription(
        db_session,
        subscription_link=_link("tg_-903"),
        password="correct horse battery",
        email="New@Mail.RU",
    )

    repo = Repository(db_session)
    refreshed = await repo.get_user(user.id)
    assert refreshed.email == "new@mail.ru"


@pytest.mark.asyncio
async def test_an_account_that_already_has_a_password_is_left_alone(db_session) -> None:
    user = await _guest_with_subscription(db_session, "tg_-904", -904)
    repo = Repository(db_session)
    await repo.update_user(user.id, web_password_hash=webauth.hash_password("original secret"))
    await db_session.commit()

    with pytest.raises(billing_api.WebAuthError, match="password_already_set"):
        await billing_api.set_web_password_by_subscription(
            db_session, subscription_link=_link("tg_-904"), password="attacker password"
        )

    still_the_owner = await repo.get_user(user.id)
    assert webauth.verify_password("original secret", still_the_owner.web_password_hash)


@pytest.mark.asyncio
async def test_a_forged_credential_is_refused(db_session) -> None:
    await _guest_with_subscription(db_session, "tg_-905", -905)
    forged = _link("tg_-905").replace("Zm9vYmFy", "AAAAAAAA")

    with pytest.raises(billing_api.WebAuthError, match="invalid_subscription"):
        await billing_api.set_web_password_by_subscription(
            db_session, subscription_link=forged, password="correct horse battery"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("link", ["", "not-a-url", "https://sub.unlockvpn.site/sub/"])
async def test_malformed_links_are_refused(db_session, link: str) -> None:
    with pytest.raises(billing_api.WebAuthError, match="invalid_subscription"):
        await billing_api.set_web_password_by_subscription(
            db_session, subscription_link=link, password="correct horse battery"
        )


@pytest.mark.asyncio
async def test_a_weak_password_is_refused_before_anything_is_looked_up(db_session) -> None:
    await _guest_with_subscription(db_session, "tg_-906", -906)

    with pytest.raises(billing_api.WebAuthError, match="weak_password"):
        await billing_api.set_web_password_by_subscription(
            db_session, subscription_link=_link("tg_-906"), password="123"
        )


@pytest.mark.asyncio
async def test_an_address_held_by_another_account_is_refused(db_session) -> None:
    await _guest_with_subscription(db_session, "tg_-907", -907)
    repo = Repository(db_session)
    other = await repo.get_or_create_user(-908)
    await repo.update_user(other.id, email="taken@mail.ru")
    await db_session.commit()

    with pytest.raises(billing_api.WebAuthError, match="email_taken"):
        await billing_api.set_web_password_by_subscription(
            db_session,
            subscription_link=_link("tg_-907"),
            password="correct horse battery",
            email="taken@mail.ru",
        )
