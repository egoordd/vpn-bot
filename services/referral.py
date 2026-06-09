from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from database.repository import Repository
from services import wallet
from services.money import percent_of
from services.tariffs import resolve_tariff

# Share of a referred user's payment credited to their referrer's wallet.
REFERRAL_REWARD_PERCENT = 20

_START_REF_PREFIX = "ref_"


class ReferralError(Exception):
    """Base class for referral attribution failures."""


class ReferralCodeNotFoundError(ReferralError):
    def __init__(self, ref_code: str):
        self.ref_code = ref_code
        super().__init__(f"Unknown referral code: {ref_code}")


class SelfReferralError(ReferralError):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__("A user cannot refer themselves")


class ReferrerAlreadySetError(ReferralError):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__("Referrer is already set for this user")


class UnknownReferralUserError(ReferralError):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"Unknown user_id={user_id}")


@dataclass(frozen=True)
class ReferralStats:
    user_id: int
    ref_code: str | None
    reward_percent: int
    referrals_count: int
    total_earned_kopecks: int


def reward_amount_for_plan(plan_code: str, *, percent: int = REFERRAL_REWARD_PERCENT) -> int:
    """Reward in kopecks for a referral whose referee bought ``plan_code``."""
    tariff = resolve_tariff(plan_code)
    return percent_of(tariff.price_rub * 100, percent)


def parse_referral_start_payload(payload: str | None) -> str | None:
    """Extract a referral code from a Telegram ``/start`` deep-link payload."""
    if not payload:
        return None
    payload = payload.strip()
    if payload.startswith(_START_REF_PREFIX):
        code = payload[len(_START_REF_PREFIX):].strip()
        return code or None
    return None


def build_referral_link(bot_username: str, ref_code: str) -> str:
    username = bot_username.lstrip("@")
    return f"https://t.me/{username}?start={_START_REF_PREFIX}{ref_code}"


async def attach_referrer(session: AsyncSession, *, user_id: int, ref_code: str) -> User:
    repo = Repository(session)
    user = await repo.get_user(user_id)
    if user is None:
        raise UnknownReferralUserError(user_id)
    if user.referrer_id is not None:
        raise ReferrerAlreadySetError(user_id)

    referrer = await repo.get_user_by_ref_code(ref_code.strip())
    if referrer is None:
        raise ReferralCodeNotFoundError(ref_code)
    if referrer.id == user_id:
        raise SelfReferralError(user_id)

    updated = await repo.update_user(user_id, referrer_id=referrer.id)
    assert updated is not None  # user existence already verified above
    return updated


async def reward_referrer_for_payment(
    session: AsyncSession,
    *,
    paid_user_id: int,
    plan_code: str,
    payment_reference: str,
    percent: int = REFERRAL_REWARD_PERCENT,
) -> wallet.WalletEntry | None:
    """Credit the referrer's wallet for a referee's completed payment.

    Idempotent on ``payment_reference``: a second call for the same payment is a
    no-op. Returns the created wallet entry, or ``None`` when there is no
    referrer / zero reward / the reward was already granted.
    """
    repo = Repository(session)
    user = await repo.get_user(paid_user_id)
    if user is None:
        raise UnknownReferralUserError(paid_user_id)
    if user.referrer_id is None:
        return None

    reward = reward_amount_for_plan(plan_code, percent=percent)
    if reward <= 0:
        return None

    existing = await repo.find_wallet_transaction(
        user.referrer_id, wallet.KIND_REFERRAL_REWARD, payment_reference
    )
    if existing is not None:
        return None

    return await wallet.deposit(
        session,
        user.referrer_id,
        reward,
        kind=wallet.KIND_REFERRAL_REWARD,
        reference=payment_reference,
        description=f"Referral reward for {plan_code}",
    )


async def get_referral_stats(
    session: AsyncSession,
    user_id: int,
    *,
    percent: int = REFERRAL_REWARD_PERCENT,
) -> ReferralStats:
    repo = Repository(session)
    user = await repo.get_user(user_id)
    if user is None:
        raise UnknownReferralUserError(user_id)
    referrals_count = await repo.count_referrals(user_id)
    total_earned = await repo.sum_wallet_amount(user_id, kind=wallet.KIND_REFERRAL_REWARD)
    return ReferralStats(
        user_id=user_id,
        ref_code=user.ref_code,
        reward_percent=percent,
        referrals_count=referrals_count,
        total_earned_kopecks=total_earned,
    )
