import base64
from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services.account_link import ClaimStatus, claim_subscription_by_link
from services.billing_api import subscription_token


def _token(panel_username: str) -> str:
    """Token shaped like the panel's: base64(<username>,<issued>) + signature."""

    head = base64.urlsafe_b64encode(f"{panel_username},1700000000".encode()).decode().rstrip("=")
    return head + "Zm9vYmFy"


def _link(panel_username: str, flavor: str = "") -> str:
    token = _token(panel_username)
    suffix = f"/{flavor}" if flavor else ""
    return f"https://sub.unlockvpn.site/sub/{token}{suffix}"


async def _website_subscription(session, panel_username: str, telegram_id: int):
    repo = Repository(session)
    owner = await repo.get_or_create_user(telegram_id)
    now = datetime.now(timezone.utc)
    subscription = await repo.create_subscription(
        user_id=owner.id,
        plan="standard_1m",
        started_at=now,
        expires_at=now + timedelta(days=30),
        panel_username=panel_username,
        # The column stores the decoded panel username, which is what the
        # link lookup resolves a token to.
        sub_token=panel_username,
        subscription_url=_link(panel_username),
    )
    await session.commit()
    return owner, subscription


def test_token_helper_decodes_like_the_real_one() -> None:
    assert subscription_token(_link("tg_-555")) == "tg_-555"


@pytest.mark.asyncio
async def test_claim_moves_website_subscription_to_the_telegram_account(db_session) -> None:
    owner, subscription = await _website_subscription(db_session, "tg_-555", -555)

    result = await claim_subscription_by_link(
        db_session, telegram_id=4242, username="buyer", link=_link("tg_-555")
    )

    assert result.status is ClaimStatus.CLAIMED
    repo = Repository(db_session)
    claimant = await repo.get_user_by_telegram_id(4242)
    assert claimant is not None
    assert result.subscription is not None
    assert result.subscription.user_id == claimant.id
    assert result.subscription.user_id != owner.id
    # The panel line keeps its name, so the customer's app is untouched.
    assert result.subscription.panel_username == "tg_-555"


@pytest.mark.asyncio
async def test_claim_accepts_a_link_with_a_flavor_suffix(db_session) -> None:
    await _website_subscription(db_session, "tg_-556", -556)

    result = await claim_subscription_by_link(
        db_session, telegram_id=4243, username=None, link=_link("tg_-556", "split")
    )

    assert result.status is ClaimStatus.CLAIMED


@pytest.mark.asyncio
async def test_claim_refuses_a_subscription_owned_by_another_telegram_account(db_session) -> None:
    await _website_subscription(db_session, "tg_777", 777)

    result = await claim_subscription_by_link(
        db_session, telegram_id=4244, username=None, link=_link("tg_777")
    )

    assert result.status is ClaimStatus.OTHER_TELEGRAM_OWNER


@pytest.mark.asyncio
async def test_claim_is_idempotent_for_the_current_owner(db_session) -> None:
    await _website_subscription(db_session, "tg_888", 888)

    result = await claim_subscription_by_link(
        db_session, telegram_id=888, username=None, link=_link("tg_888")
    )

    assert result.status is ClaimStatus.ALREADY_YOURS


@pytest.mark.asyncio
async def test_claim_rejects_a_forged_credential(db_session) -> None:
    await _website_subscription(db_session, "tg_-557", -557)
    forged = _link("tg_-557").replace("Zm9vYmFy", "AAAAAAAA")

    result = await claim_subscription_by_link(
        db_session, telegram_id=4245, username=None, link=forged
    )

    assert result.status is ClaimStatus.INVALID_LINK


@pytest.mark.asyncio
@pytest.mark.parametrize("link", ["", "not-a-url", "https://sub.unlockvpn.site/sub/", "хех"])
async def test_claim_rejects_malformed_links(db_session, link: str) -> None:
    result = await claim_subscription_by_link(
        db_session, telegram_id=4246, username=None, link=link
    )

    assert result.status is ClaimStatus.INVALID_LINK


@pytest.mark.asyncio
async def test_attaching_telegram_moves_the_website_subscription_over(db_session) -> None:
    from services.account_link import attach_telegram_to_web_account

    web_owner, subscription = await _website_subscription(db_session, "tg_-910", -910)
    repo = Repository(db_session)
    await repo.update_user(web_owner.id, email="guest@mail.ru")
    await db_session.commit()

    surviving = await attach_telegram_to_web_account(
        db_session, web_telegram_id=-910, telegram_id=5150, username="buyer"
    )

    assert surviving == 5150
    telegram_account = await repo.get_user_by_telegram_id(5150)
    assert telegram_account is not None
    moved = await repo.get_subscription(subscription.id)
    assert moved.user_id == telegram_account.id
    # The address follows so receipts keep landing where the buyer expects.
    assert telegram_account.email == "guest@mail.ru"


@pytest.mark.asyncio
async def test_attaching_never_overwrites_an_address_the_telegram_account_already_has(
    db_session,
) -> None:
    from services.account_link import attach_telegram_to_web_account

    web_owner, _ = await _website_subscription(db_session, "tg_-911", -911)
    repo = Repository(db_session)
    await repo.update_user(web_owner.id, email="guest@mail.ru")
    existing = await repo.get_or_create_user(5151)
    await repo.update_user(existing.id, email="mine@mail.ru")
    await db_session.commit()

    await attach_telegram_to_web_account(
        db_session, web_telegram_id=-911, telegram_id=5151, username=None
    )

    refreshed = await repo.get_user_by_telegram_id(5151)
    assert refreshed.email == "mine@mail.ru"


@pytest.mark.asyncio
async def test_two_real_telegram_accounts_are_never_merged(db_session) -> None:
    from services.account_link import attach_telegram_to_web_account

    owner, subscription = await _website_subscription(db_session, "tg_912", 912)

    surviving = await attach_telegram_to_web_account(
        db_session, web_telegram_id=912, telegram_id=5152, username=None
    )

    assert surviving == 5152
    repo = Repository(db_session)
    untouched = await repo.get_subscription(subscription.id)
    assert untouched.user_id == owner.id
