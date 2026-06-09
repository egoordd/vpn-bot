import pytest

from database.repository import Repository
from services import wallet
from services.wallet import (
    InsufficientBalanceError,
    UnknownWalletUserError,
    deposit,
    get_balance,
    get_wallet_snapshot,
    spend,
)


async def _make_user(db_session, telegram_id: int = 5001):
    return await Repository(db_session).create_user(telegram_id=telegram_id, username="wallet")


@pytest.mark.asyncio
async def test_deposit_increments_balance_and_records_entry(db_session):
    user = await _make_user(db_session)

    entry = await deposit(db_session, user.id, 14900, reference="topup-1", description="Top up")

    assert entry.amount_kopecks == 14900
    assert entry.balance_after_kopecks == 14900
    assert entry.kind == wallet.KIND_DEPOSIT
    assert await get_balance(db_session, user.id) == 14900


@pytest.mark.asyncio
async def test_sequential_transactions_track_running_balance(db_session):
    user = await _make_user(db_session)

    await deposit(db_session, user.id, 20000)
    spent = await spend(db_session, user.id, 14900, reference="plan:standard_1m")
    bonus = await deposit(db_session, user.id, 5000, kind=wallet.KIND_PROMO_BONUS)

    assert spent.amount_kopecks == -14900
    assert spent.balance_after_kopecks == 5100
    assert bonus.balance_after_kopecks == 10100
    assert await get_balance(db_session, user.id) == 10100


@pytest.mark.asyncio
async def test_spend_more_than_balance_raises_and_keeps_balance(db_session):
    user = await _make_user(db_session)
    await deposit(db_session, user.id, 1000)

    with pytest.raises(InsufficientBalanceError) as exc:
        await spend(db_session, user.id, 5000)

    assert exc.value.required == 5000
    assert exc.value.available == 1000
    assert await get_balance(db_session, user.id) == 1000


@pytest.mark.asyncio
async def test_operations_on_unknown_user_raise(db_session):
    with pytest.raises(UnknownWalletUserError):
        await get_balance(db_session, 999999)
    with pytest.raises(UnknownWalletUserError):
        await deposit(db_session, 999999, 100)
    with pytest.raises(UnknownWalletUserError):
        await spend(db_session, 999999, 100)


@pytest.mark.asyncio
async def test_deposit_rejects_non_positive_amount_and_wrong_kind(db_session):
    user = await _make_user(db_session)
    with pytest.raises(ValueError):
        await deposit(db_session, user.id, 0)
    with pytest.raises(ValueError):
        await deposit(db_session, user.id, 100, kind=wallet.KIND_SPEND)
    with pytest.raises(ValueError):
        await spend(db_session, user.id, -1)


@pytest.mark.asyncio
async def test_snapshot_returns_balance_and_entries_newest_first(db_session):
    user = await _make_user(db_session)
    await deposit(db_session, user.id, 10000)
    await spend(db_session, user.id, 2500)

    snapshot = await get_wallet_snapshot(db_session, user.id)

    assert snapshot.balance_kopecks == 7500
    assert [entry.amount_kopecks for entry in snapshot.entries] == [-2500, 10000]


@pytest.mark.asyncio
async def test_snapshot_on_unknown_user_raises(db_session):
    with pytest.raises(UnknownWalletUserError):
        await get_wallet_snapshot(db_session, 999999)
