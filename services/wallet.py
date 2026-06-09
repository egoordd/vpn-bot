from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WalletTransaction
from database.repository import Repository

# Ledger entry kinds (see WalletTransaction.kind).
KIND_DEPOSIT = "deposit"
KIND_SPEND = "spend"
KIND_REFERRAL_REWARD = "referral_reward"
KIND_PROMO_BONUS = "promo_bonus"
KIND_REFUND = "refund"
KIND_ADJUSTMENT = "adjustment"

CREDIT_KINDS = frozenset({KIND_DEPOSIT, KIND_REFERRAL_REWARD, KIND_PROMO_BONUS, KIND_REFUND, KIND_ADJUSTMENT})
DEBIT_KINDS = frozenset({KIND_SPEND})


class WalletError(Exception):
    """Base class for wallet-related failures."""


class UnknownWalletUserError(WalletError):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"Unknown wallet user_id={user_id}")


class InsufficientBalanceError(WalletError):
    def __init__(self, *, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__(f"Insufficient balance: required={required}, available={available}")


@dataclass(frozen=True)
class WalletEntry:
    id: int
    amount_kopecks: int
    balance_after_kopecks: int
    kind: str
    reference: str | None
    description: str | None
    created_at: datetime


@dataclass(frozen=True)
class WalletSnapshot:
    user_id: int
    balance_kopecks: int
    entries: tuple[WalletEntry, ...]


def _entry_from_model(transaction: WalletTransaction) -> WalletEntry:
    return WalletEntry(
        id=transaction.id,
        amount_kopecks=transaction.amount,
        balance_after_kopecks=transaction.balance_after,
        kind=transaction.kind,
        reference=transaction.reference,
        description=transaction.description,
        created_at=transaction.created_at,
    )


async def get_balance(session: AsyncSession, user_id: int) -> int:
    balance = await Repository(session).get_balance(user_id)
    if balance is None:
        raise UnknownWalletUserError(user_id)
    return balance


async def deposit(
    session: AsyncSession,
    user_id: int,
    amount_kopecks: int,
    *,
    kind: str = KIND_DEPOSIT,
    reference: str | None = None,
    description: str | None = None,
) -> WalletEntry:
    if amount_kopecks <= 0:
        raise ValueError("deposit amount must be positive")
    if kind not in CREDIT_KINDS:
        raise ValueError(f"{kind!r} is not a credit kind")
    transaction = await Repository(session).credit_balance(
        user_id=user_id,
        amount=amount_kopecks,
        kind=kind,
        reference=reference,
        description=description,
    )
    if transaction is None:
        raise UnknownWalletUserError(user_id)
    return _entry_from_model(transaction)


async def spend(
    session: AsyncSession,
    user_id: int,
    amount_kopecks: int,
    *,
    reference: str | None = None,
    description: str | None = None,
) -> WalletEntry:
    if amount_kopecks <= 0:
        raise ValueError("spend amount must be positive")
    repo = Repository(session)
    balance = await repo.get_balance(user_id)
    if balance is None:
        raise UnknownWalletUserError(user_id)
    transaction = await repo.debit_balance(
        user_id=user_id,
        amount=amount_kopecks,
        kind=KIND_SPEND,
        reference=reference,
        description=description,
    )
    if transaction is None:
        raise InsufficientBalanceError(required=amount_kopecks, available=balance)
    return _entry_from_model(transaction)


async def get_wallet_snapshot(
    session: AsyncSession,
    user_id: int,
    *,
    history_limit: int = 20,
) -> WalletSnapshot:
    repo = Repository(session)
    balance = await repo.get_balance(user_id)
    if balance is None:
        raise UnknownWalletUserError(user_id)
    transactions = await repo.list_wallet_transactions(user_id, limit=history_limit)
    return WalletSnapshot(
        user_id=user_id,
        balance_kopecks=balance,
        entries=tuple(_entry_from_model(item) for item in transactions),
    )
