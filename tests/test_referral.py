import pytest

from database.repository import Repository
from services import wallet
from services.referral import (
    REFERRAL_REWARD_PERCENT,
    ReferralCodeNotFoundError,
    ReferrerAlreadySetError,
    SelfReferralError,
    UnknownReferralUserError,
    attach_referrer,
    build_referral_link,
    get_referral_stats,
    parse_referral_start_payload,
    reward_amount_for_plan,
    reward_referrer_for_payment,
)


async def _user(db_session, telegram_id: int):
    return await Repository(db_session).create_user(telegram_id=telegram_id, username=f"u{telegram_id}")


@pytest.mark.unit
def test_reward_amount_for_plan_is_percent_of_price():
    # standard_1m: 149 RUB -> 14900 kopecks -> 20% = 2980
    assert reward_amount_for_plan("standard_1m") == 2980
    assert reward_amount_for_plan("standard_1m", percent=0) == 0
    assert REFERRAL_REWARD_PERCENT == 20


@pytest.mark.unit
def test_parse_referral_start_payload():
    assert parse_referral_start_payload("ref_tg5001") == "tg5001"
    assert parse_referral_start_payload("ref_") is None
    assert parse_referral_start_payload("just_start") is None
    assert parse_referral_start_payload(None) is None


@pytest.mark.unit
def test_build_referral_link_strips_at_sign():
    assert build_referral_link("@unlock_bot", "tg5001") == "https://t.me/unlock_bot?start=ref_tg5001"


@pytest.mark.asyncio
async def test_attach_referrer_sets_referrer(db_session):
    referrer = await _user(db_session, 7001)
    referee = await _user(db_session, 7002)

    updated = await attach_referrer(db_session, user_id=referee.id, ref_code=referrer.ref_code)

    assert updated.referrer_id == referrer.id


@pytest.mark.asyncio
async def test_attach_referrer_rejects_invalid_attempts(db_session):
    referrer = await _user(db_session, 7001)
    referee = await _user(db_session, 7002)

    with pytest.raises(ReferralCodeNotFoundError):
        await attach_referrer(db_session, user_id=referee.id, ref_code="nope")

    with pytest.raises(SelfReferralError):
        await attach_referrer(db_session, user_id=referrer.id, ref_code=referrer.ref_code)

    with pytest.raises(UnknownReferralUserError):
        await attach_referrer(db_session, user_id=999999, ref_code=referrer.ref_code)

    await attach_referrer(db_session, user_id=referee.id, ref_code=referrer.ref_code)
    with pytest.raises(ReferrerAlreadySetError):
        await attach_referrer(db_session, user_id=referee.id, ref_code=referrer.ref_code)


@pytest.mark.asyncio
async def test_reward_referrer_credits_wallet_and_is_idempotent(db_session):
    referrer = await _user(db_session, 7001)
    referee = await _user(db_session, 7002)
    await attach_referrer(db_session, user_id=referee.id, ref_code=referrer.ref_code)

    entry = await reward_referrer_for_payment(
        db_session, paid_user_id=referee.id, plan_code="standard_1m", payment_reference="pay-1"
    )
    assert entry is not None
    assert entry.amount_kopecks == 2980
    assert entry.kind == wallet.KIND_REFERRAL_REWARD
    assert await wallet.get_balance(db_session, referrer.id) == 2980

    repeat = await reward_referrer_for_payment(
        db_session, paid_user_id=referee.id, plan_code="standard_1m", payment_reference="pay-1"
    )
    assert repeat is None
    assert await wallet.get_balance(db_session, referrer.id) == 2980


@pytest.mark.asyncio
async def test_reward_referrer_without_referrer_returns_none(db_session):
    solo = await _user(db_session, 7003)
    result = await reward_referrer_for_payment(
        db_session, paid_user_id=solo.id, plan_code="standard_1m", payment_reference="pay-x"
    )
    assert result is None


@pytest.mark.asyncio
async def test_reward_referrer_zero_percent_returns_none(db_session):
    referrer = await _user(db_session, 7001)
    referee = await _user(db_session, 7002)
    await attach_referrer(db_session, user_id=referee.id, ref_code=referrer.ref_code)

    result = await reward_referrer_for_payment(
        db_session,
        paid_user_id=referee.id,
        plan_code="standard_1m",
        payment_reference="pay-z",
        percent=0,
    )

    assert result is None
    assert await wallet.get_balance(db_session, referrer.id) == 0


@pytest.mark.asyncio
async def test_reward_and_stats_reject_unknown_user(db_session):
    with pytest.raises(UnknownReferralUserError):
        await reward_referrer_for_payment(
            db_session, paid_user_id=999999, plan_code="standard_1m", payment_reference="x"
        )
    with pytest.raises(UnknownReferralUserError):
        await get_referral_stats(db_session, 999999)


@pytest.mark.asyncio
async def test_get_referral_stats_counts_and_sums(db_session):
    referrer = await _user(db_session, 7001)
    referee_a = await _user(db_session, 7002)
    referee_b = await _user(db_session, 7004)
    await attach_referrer(db_session, user_id=referee_a.id, ref_code=referrer.ref_code)
    await attach_referrer(db_session, user_id=referee_b.id, ref_code=referrer.ref_code)
    await reward_referrer_for_payment(
        db_session, paid_user_id=referee_a.id, plan_code="standard_1m", payment_reference="pay-a"
    )

    stats = await get_referral_stats(db_session, referrer.id)

    assert stats.referrals_count == 2
    assert stats.total_earned_kopecks == 2980
    assert stats.reward_percent == 20
    assert stats.ref_code == referrer.ref_code
