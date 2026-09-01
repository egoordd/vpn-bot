from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from database.repository import Repository

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
    """Who a user brought in. There is no payout attached: rewards used to be a
    share of the referee's payment credited to a wallet, and the wallet is gone.
    Attribution is kept because the funnel and ad-source reporting run on it."""

    user_id: int
    ref_code: str | None
    referrals_count: int


def parse_referral_start_payload(payload: str | None) -> str | None:
    """Extract a referral code from a Telegram ``/start`` deep-link payload."""
    if not payload:
        return None
    payload = payload.strip()
    if payload.startswith(_START_REF_PREFIX):
        code = payload[len(_START_REF_PREFIX):].strip()
        return code or None
    return None


_START_SRC_PREFIX = "src_"
_SRC_MAX_LEN = 32
_SRC_RE = re.compile(r"[^a-z0-9_-]+")


def normalize_source_slug(raw: str | None) -> str | None:
    """Canonical campaign slug: lowercase, ``[a-z0-9_-]`` only, ≤32 chars.

    Shared by the bot deep-link and the site's /go/<campaign> redirect so the
    same campaign never splits into two rows in the funnel (e.g. "Instagram"
    from a link and "instagram" from another both become ``instagram``).
    Returns None when nothing usable survives — notably for Cyrillic-only
    names, which sanitise away entirely.
    """
    if not raw:
        return None
    slug = _SRC_RE.sub("", raw.strip().lower())[:_SRC_MAX_LEN].strip("-_")
    return slug or None


def parse_source_start_payload(payload: str | None) -> str | None:
    """Extract an acquisition source from a ``/start src_<name>`` deep-link.

    Used to tag where a user came from (seeded channels, ads) so the funnel can
    be compared by source. Sanitised to a short slug; None when absent/empty.
    """
    if not payload:
        return None
    payload = payload.strip()
    if not payload.startswith(_START_SRC_PREFIX):
        return None
    return normalize_source_slug(payload[len(_START_SRC_PREFIX):])


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


async def get_referral_stats(session: AsyncSession, user_id: int) -> ReferralStats:
    repo = Repository(session)
    user = await repo.get_user(user_id)
    if user is None:
        raise UnknownReferralUserError(user_id)
    referrals_count = await repo.count_referrals(user_id)
    return ReferralStats(
        user_id=user_id,
        ref_code=user.ref_code,
        referrals_count=referrals_count,
    )
