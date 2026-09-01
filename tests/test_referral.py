import pytest

from database.repository import Repository
from services.referral import (
    ReferralCodeNotFoundError,
    ReferrerAlreadySetError,
    SelfReferralError,
    UnknownReferralUserError,
    attach_referrer,
    build_referral_link,
    get_referral_stats,
    parse_referral_start_payload,
)


async def _user(db_session, telegram_id: int):
    return await Repository(db_session).create_user(telegram_id=telegram_id, username=f"u{telegram_id}")

@pytest.mark.unit
def test_parse_referral_start_payload():
    assert parse_referral_start_payload("ref_tg5001") == "tg5001"
    assert parse_referral_start_payload("ref_") is None
    assert parse_referral_start_payload("just_start") is None
    assert parse_referral_start_payload(None) is None


@pytest.mark.unit
def test_parse_source_start_payload():
    from services.referral import parse_source_start_payload

    assert parse_source_start_payload("src_telegram_channel") == "telegram_channel"
    assert parse_source_start_payload("src_VC-Blog") == "vc-blog"  # lowercased, dash kept
    # non [a-z0-9_-] chars (cyrillic, punctuation) are stripped → empty → None
    assert parse_source_start_payload("src_реклама") is None
    assert parse_source_start_payload("src_") is None
    assert parse_source_start_payload("ref_tg5001") is None  # referral, not a source
    assert parse_source_start_payload(None) is None
    # sanitised + length-capped
    long = "src_" + "a" * 100
    assert len(parse_source_start_payload(long)) == 32


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


@pytest.mark.asyncio
async def test_get_referral_stats_counts_who_was_brought_in(db_session):
    referrer = await _user(db_session, 7001)
    referee_a = await _user(db_session, 7002)
    referee_b = await _user(db_session, 7004)
    await attach_referrer(db_session, user_id=referee_a.id, ref_code=referrer.ref_code)
    await attach_referrer(db_session, user_id=referee_b.id, ref_code=referrer.ref_code)

    stats = await get_referral_stats(db_session, referrer.id)

    assert stats.referrals_count == 2
    assert stats.ref_code == referrer.ref_code


@pytest.mark.asyncio
async def test_get_referral_stats_rejects_unknown_user(db_session):
    with pytest.raises(UnknownReferralUserError):
        await get_referral_stats(db_session, 999999)


# --- campaign slug normalization (shared by bot deep-link and site /go/) ------

def test_normalize_source_slug_canonicalises_case_and_charset():
    from services.referral import normalize_source_slug

    # same campaign written differently must collapse to one slug, or the
    # funnel would show it as two separate channels
    assert normalize_source_slug("Instagram") == "instagram"
    assert normalize_source_slug("  TG-Ads_Jul  ") == "tg-ads_jul"
    assert normalize_source_slug("blogger ivan!") == "bloggerivan"


def test_normalize_source_slug_truncates_and_trims():
    from services.referral import normalize_source_slug

    assert normalize_source_slug("a" * 50) == "a" * 32
    assert normalize_source_slug("__promo--") == "promo"


def test_normalize_source_slug_none_when_nothing_usable():
    from services.referral import normalize_source_slug

    # Cyrillic sanitises away entirely — must be None, not an empty label
    assert normalize_source_slug("инстаграм") is None
    assert normalize_source_slug("___") is None
    assert normalize_source_slug("") is None
    assert normalize_source_slug(None) is None
