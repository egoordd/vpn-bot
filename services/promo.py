from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PromoCode
from database.repository import Repository
from services import wallet
from services.money import percent_of

# Promo kinds and the meaning of PromoCode.value for each:
#   balance_bonus   -> value is kopecks credited to the wallet on redemption
#   percent_discount-> value is a percentage off a checkout amount
#   fixed_discount  -> value is kopecks off a checkout amount
PROMO_BALANCE_BONUS = "balance_bonus"
PROMO_PERCENT_DISCOUNT = "percent_discount"
PROMO_FIXED_DISCOUNT = "fixed_discount"

DISCOUNT_KINDS = frozenset({PROMO_PERCENT_DISCOUNT, PROMO_FIXED_DISCOUNT})


class PromoError(Exception):
    """Base class for promo code failures."""


class PromoNotFoundError(PromoError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Unknown promo code: {code}")


class PromoInactiveError(PromoError):
    pass


class PromoExpiredError(PromoError):
    pass


class PromoExhaustedError(PromoError):
    pass


class PromoUserLimitError(PromoError):
    pass


class PromoMinAmountError(PromoError):
    def __init__(self, *, required: int, actual: int):
        self.required = required
        self.actual = actual
        super().__init__(f"Order amount {actual} is below promo minimum {required}")


class PromoTypeError(PromoError):
    pass


@dataclass(frozen=True)
class DiscountResult:
    code: str
    original_kopecks: int
    discount_kopecks: int
    final_kopecks: int


@dataclass(frozen=True)
class PromoRedemptionResult:
    code: str
    kind: str
    credited_kopecks: int
    wallet_entry: wallet.WalletEntry | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _check_live(promo: PromoCode) -> None:
    if not promo.is_active:
        raise PromoInactiveError(promo.code)
    if promo.expires_at is not None and _aware(promo.expires_at) <= _now():
        raise PromoExpiredError(promo.code)


def _check_exhausted(promo: PromoCode) -> None:
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        raise PromoExhaustedError(promo.code)


async def _check_user_limit(repo: Repository, promo: PromoCode, user_id: int) -> None:
    used_by_user = await repo.count_user_redemptions(promo.code, user_id)
    if used_by_user >= promo.per_user_limit:
        raise PromoUserLimitError(promo.code)


def compute_discount(promo: PromoCode, amount_kopecks: int) -> int:
    if promo.kind == PROMO_PERCENT_DISCOUNT:
        discount = percent_of(amount_kopecks, promo.value)
    elif promo.kind == PROMO_FIXED_DISCOUNT:
        discount = promo.value
    else:  # pragma: no cover - guarded by callers
        raise PromoTypeError(promo.code)
    return min(max(discount, 0), amount_kopecks)


async def redeem_balance_promo(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
) -> PromoRedemptionResult:
    repo = Repository(session)
    promo = await repo.get_promo_code(code.strip())
    if promo is None:
        raise PromoNotFoundError(code)
    if promo.kind != PROMO_BALANCE_BONUS:
        raise PromoTypeError(promo.code)

    _check_live(promo)
    await _check_user_limit(repo, promo, user_id)

    if await repo.claim_promo_use(promo.code) is None:
        raise PromoExhaustedError(promo.code)

    await repo.create_promo_redemption(promo.code, user_id, applied_amount=promo.value)
    entry = await wallet.deposit(
        session,
        user_id,
        promo.value,
        kind=wallet.KIND_PROMO_BONUS,
        reference=f"promo:{promo.code}",
        description=f"Promo bonus {promo.code}",
    )
    return PromoRedemptionResult(
        code=promo.code,
        kind=promo.kind,
        credited_kopecks=promo.value,
        wallet_entry=entry,
    )


async def preview_discount(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
    amount_kopecks: int,
) -> DiscountResult:
    repo = Repository(session)
    promo = await repo.get_promo_code(code.strip())
    if promo is None:
        raise PromoNotFoundError(code)
    if promo.kind not in DISCOUNT_KINDS:
        raise PromoTypeError(promo.code)

    _check_live(promo)
    _check_exhausted(promo)
    await _check_user_limit(repo, promo, user_id)

    if promo.min_amount_kopecks is not None and amount_kopecks < promo.min_amount_kopecks:
        raise PromoMinAmountError(required=promo.min_amount_kopecks, actual=amount_kopecks)

    discount = compute_discount(promo, amount_kopecks)
    return DiscountResult(
        code=promo.code,
        original_kopecks=amount_kopecks,
        discount_kopecks=discount,
        final_kopecks=amount_kopecks - discount,
    )


async def apply_discount(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
    amount_kopecks: int,
    reference: str | None = None,
) -> DiscountResult:
    result = await preview_discount(
        session, user_id=user_id, code=code, amount_kopecks=amount_kopecks
    )
    repo = Repository(session)
    if await repo.claim_promo_use(result.code) is None:
        raise PromoExhaustedError(result.code)
    await repo.create_promo_redemption(
        result.code, user_id, applied_amount=result.discount_kopecks, reference=reference
    )
    return result
