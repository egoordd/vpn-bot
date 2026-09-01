from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services import promo
from services.promo import (
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
)


async def _user(db_session, telegram_id: int):
    return await Repository(db_session).create_user(telegram_id=telegram_id, username=f"u{telegram_id}")


async def _promo(db_session, **kwargs):
    return await Repository(db_session).create_promo_code(**kwargs)


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
    await _promo(db_session, code="SUMMER25", kind=promo.PROMO_SUBSCRIPTION_GRANT, value=30)

    result = await promo.redeem_subscription_promo(db_session, user_id=user.id, code="  summer25 ")

    assert result.granted_days == 30
    assert result.code == "SUMMER25"
    # per-user limit still counts across case variants
    with pytest.raises(PromoUserLimitError):
        await promo.redeem_subscription_promo(db_session, user_id=user.id, code="Summer25")


@pytest.mark.asyncio
async def test_promo_codes_are_stored_uppercase(db_session):
    repo = Repository(db_session)
    created = await repo.create_promo_code(
        code=" bonus10 ", kind=promo.PROMO_SUBSCRIPTION_GRANT, value=30
    )
    assert created.code == "BONUS10"
    assert (await repo.get_promo_code("bonus10")).code == "BONUS10"


@pytest.mark.integration
async def test_subscription_promo_hands_over_access_not_money(session_pool):
    """A grant is worth days, not money."""
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=920001)
        await repo.create_promo_code(
            code="FREEMONTH", kind=promo.PROMO_SUBSCRIPTION_GRANT, value=30, max_uses=3
        )
        await session.commit()

        result = await promo.redeem_subscription_promo(
            session, user_id=user.id, code="freemonth"
        )
        assert result.granted_days == 30
        assert result.plan == "standard_1m"
        assert result.credited_kopecks == 0


@pytest.mark.integration
async def test_subscription_promo_refuses_a_length_no_tariff_sells(session_pool):
    """Rounding to the nearest tariff would quietly hand out a different length
    than the code promises."""
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=920002)
        await repo.create_promo_code(
            code="ODDDAYS", kind=promo.PROMO_SUBSCRIPTION_GRANT, value=17, max_uses=1
        )
        await session.commit()
        with pytest.raises(promo.PromoTypeError):
            await promo.redeem_subscription_promo(session, user_id=user.id, code="ODDDAYS")


@pytest.mark.integration
async def test_subscription_promo_runs_out_after_its_uses(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        await repo.create_promo_code(
            code="TWICE", kind=promo.PROMO_SUBSCRIPTION_GRANT, value=30, max_uses=2
        )
        users = [await repo.create_user(telegram_id=920100 + i) for i in range(3)]
        await session.commit()

        for u in users[:2]:
            await promo.redeem_subscription_promo(session, user_id=u.id, code="TWICE")
        with pytest.raises(promo.PromoExhaustedError):
            await promo.redeem_subscription_promo(session, user_id=users[2].id, code="TWICE")


@pytest.mark.integration
async def test_discount_promo_still_refuses_the_subscription_path(session_pool):
    """The kinds must not be interchangeable — a discount code redeemed as a
    grant would hand out free access nobody authorised."""
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=920003)
        await repo.create_promo_code(
            code="TENOFF", kind=promo.PROMO_PERCENT_DISCOUNT, value=10, max_uses=1
        )
        await session.commit()
        with pytest.raises(promo.PromoTypeError):
            await promo.redeem_subscription_promo(session, user_id=user.id, code="TENOFF")
