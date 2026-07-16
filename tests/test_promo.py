from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services import wallet
from services.promo import (
    PROMO_BALANCE_BONUS,
    PROMO_FIXED_DISCOUNT,
    PROMO_PERCENT_DISCOUNT,
    PromoExhaustedError,
    PromoExpiredError,
    PromoInactiveError,
    PromoMinAmountError,
    PromoNotFoundError,
    PromoTypeError,
    PromoUserLimitError,
    apply_discount,
    preview_discount,
    redeem_balance_promo,
)


async def _user(db_session, telegram_id: int):
    return await Repository(db_session).create_user(telegram_id=telegram_id, username=f"u{telegram_id}")


async def _promo(db_session, **kwargs):
    return await Repository(db_session).create_promo_code(**kwargs)


@pytest.mark.asyncio
async def test_redeem_balance_promo_credits_wallet(db_session):
    user = await _user(db_session, 8001)
    await _promo(db_session, code="WELCOME", kind=PROMO_BALANCE_BONUS, value=5000, max_uses=10)

    result = await redeem_balance_promo(db_session, user_id=user.id, code="WELCOME")

    assert result.credited_kopecks == 5000
    assert result.wallet_entry is not None
    assert result.wallet_entry.kind == wallet.KIND_PROMO_BONUS
    assert await wallet.get_balance(db_session, user.id) == 5000
    promo = await Repository(db_session).get_promo_code("WELCOME")
    assert promo.used_count == 1


@pytest.mark.asyncio
async def test_redeem_balance_promo_enforces_per_user_limit(db_session):
    user = await _user(db_session, 8002)
    await _promo(db_session, code="ONCE", kind=PROMO_BALANCE_BONUS, value=1000, per_user_limit=1)

    await redeem_balance_promo(db_session, user_id=user.id, code="ONCE")
    with pytest.raises(PromoUserLimitError):
        await redeem_balance_promo(db_session, user_id=user.id, code="ONCE")
    assert await wallet.get_balance(db_session, user.id) == 1000


@pytest.mark.asyncio
async def test_redeem_balance_promo_exhausts_global_uses(db_session):
    first = await _user(db_session, 8003)
    second = await _user(db_session, 8004)
    await _promo(db_session, code="LIMITED", kind=PROMO_BALANCE_BONUS, value=1000, max_uses=1)

    await redeem_balance_promo(db_session, user_id=first.id, code="LIMITED")
    with pytest.raises(PromoExhaustedError):
        await redeem_balance_promo(db_session, user_id=second.id, code="LIMITED")


@pytest.mark.asyncio
async def test_redeem_balance_promo_rejects_inactive_expired_and_wrong_type(db_session):
    user = await _user(db_session, 8005)
    await _promo(db_session, code="OFF", kind=PROMO_BALANCE_BONUS, value=1000, is_active=False)
    await _promo(
        db_session,
        code="OLD",
        kind=PROMO_BALANCE_BONUS,
        value=1000,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    await _promo(db_session, code="SALE", kind=PROMO_PERCENT_DISCOUNT, value=20)

    with pytest.raises(PromoInactiveError):
        await redeem_balance_promo(db_session, user_id=user.id, code="OFF")
    with pytest.raises(PromoExpiredError):
        await redeem_balance_promo(db_session, user_id=user.id, code="OLD")
    with pytest.raises(PromoTypeError):
        await redeem_balance_promo(db_session, user_id=user.id, code="SALE")
    with pytest.raises(PromoNotFoundError):
        await redeem_balance_promo(db_session, user_id=user.id, code="GHOST")


@pytest.mark.asyncio
async def test_preview_percent_discount(db_session):
    user = await _user(db_session, 8006)
    await _promo(db_session, code="MINUS20", kind=PROMO_PERCENT_DISCOUNT, value=20)

    result = await preview_discount(db_session, user_id=user.id, code="MINUS20", amount_kopecks=14900)

    assert result.discount_kopecks == 2980
    assert result.final_kopecks == 11920


@pytest.mark.asyncio
async def test_preview_fixed_discount_is_capped_at_amount(db_session):
    user = await _user(db_session, 8007)
    await _promo(db_session, code="CUT", kind=PROMO_FIXED_DISCOUNT, value=20000)

    result = await preview_discount(db_session, user_id=user.id, code="CUT", amount_kopecks=14900)

    assert result.discount_kopecks == 14900
    assert result.final_kopecks == 0


@pytest.mark.asyncio
async def test_preview_discount_enforces_min_amount(db_session):
    user = await _user(db_session, 8008)
    await _promo(
        db_session,
        code="BIG",
        kind=PROMO_PERCENT_DISCOUNT,
        value=10,
        min_amount_kopecks=50000,
    )

    with pytest.raises(PromoMinAmountError):
        await preview_discount(db_session, user_id=user.id, code="BIG", amount_kopecks=14900)


@pytest.mark.asyncio
async def test_preview_discount_rejects_balance_promo_type(db_session):
    user = await _user(db_session, 8009)
    await _promo(db_session, code="BONUS", kind=PROMO_BALANCE_BONUS, value=1000)

    with pytest.raises(PromoTypeError):
        await preview_discount(db_session, user_id=user.id, code="BONUS", amount_kopecks=14900)


@pytest.mark.asyncio
async def test_preview_discount_unknown_code_raises(db_session):
    user = await _user(db_session, 8011)
    with pytest.raises(PromoNotFoundError):
        await preview_discount(db_session, user_id=user.id, code="GHOST", amount_kopecks=14900)


@pytest.mark.asyncio
async def test_apply_discount_consumes_use_and_then_exhausts(db_session):
    user = await _user(db_session, 8010)
    await _promo(db_session, code="SINGLE", kind=PROMO_PERCENT_DISCOUNT, value=50, max_uses=1)

    result = await apply_discount(
        db_session, user_id=user.id, code="SINGLE", amount_kopecks=10000, reference="order-1"
    )
    assert result.final_kopecks == 5000
    promo = await Repository(db_session).get_promo_code("SINGLE")
    assert promo.used_count == 1

    with pytest.raises(PromoExhaustedError):
        await preview_discount(db_session, user_id=user.id, code="SINGLE", amount_kopecks=10000)


@pytest.mark.asyncio
async def test_promo_lookup_is_case_insensitive(db_session):
    # Users type codes from phone keyboards in any case — "test1000" must
    # find TEST1000 (live complaint 2026-07-16: «промокоды не работают»).
    user = await _user(db_session, 8077)
    await _promo(db_session, code="SUMMER25", kind=PROMO_BALANCE_BONUS, value=2500)

    result = await redeem_balance_promo(db_session, user_id=user.id, code="  summer25 ")

    assert result.credited_kopecks == 2500
    assert result.code == "SUMMER25"
    # per-user limit still counts across case variants
    with pytest.raises(PromoUserLimitError):
        await redeem_balance_promo(db_session, user_id=user.id, code="Summer25")


@pytest.mark.asyncio
async def test_promo_codes_are_stored_uppercase(db_session):
    repo = Repository(db_session)
    created = await repo.create_promo_code(code=" bonus10 ", kind=PROMO_BALANCE_BONUS, value=1000)
    assert created.code == "BONUS10"
    assert (await repo.get_promo_code("bonus10")).code == "BONUS10"
