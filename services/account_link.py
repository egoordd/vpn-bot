"""Attach a subscription bought on the website to a Telegram account.

A website purchase creates its own user under a synthetic negative telegram_id,
because there is no chat behind an email address. The buyer then opens the bot,
sees an empty account, and concludes the payment vanished. Two of the first
three support tickets we looked at were exactly this.

Matching on the email address is not an option and never will be: an address is
public, so accepting one as proof would hand anybody the subscription of anyone
whose address they can guess. The subscription link is different — it carries an
opaque credential the panel signed, and the renewal path already treats it as
proof of ownership. This module reuses that same standard.

What it deliberately refuses:
  * a link whose credential does not match the stored one, byte for byte;
  * a subscription already owned by a *different* real Telegram account, so a
    leaked link cannot be used to take over someone's account.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Subscription
from database.repository import Repository
from services.billing_api import _subscription_credential, subscription_token


class ClaimStatus(str, Enum):
    CLAIMED = "claimed"
    ALREADY_YOURS = "already_yours"
    OTHER_TELEGRAM_OWNER = "other_telegram_owner"
    INVALID_LINK = "invalid_link"


@dataclass(frozen=True)
class ClaimResult:
    status: ClaimStatus
    subscription: Subscription | None = None


async def claim_subscription_by_link(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    link: str,
) -> ClaimResult:
    """Move the subscription behind `link` onto this Telegram account.

    The panel line is left untouched: its name only labels the account inside
    the panel, and the token stays the same, so the customer's app keeps working
    and a later renewal extends the very same line.
    """

    credential = _subscription_credential(link)
    token = subscription_token(link)
    if credential is None or token is None:
        return ClaimResult(ClaimStatus.INVALID_LINK)

    repo = Repository(session)
    subscription = await repo.get_subscription_by_token(token)
    if subscription is None:
        return ClaimResult(ClaimStatus.INVALID_LINK)

    stored = _subscription_credential(subscription.subscription_url)
    # A wrong credential and an unknown subscription answer identically on
    # purpose: telling them apart would confirm which links exist.
    if stored is None or not secrets.compare_digest(credential, stored):
        return ClaimResult(ClaimStatus.INVALID_LINK)

    owner = await repo.get_user(subscription.user_id)
    if owner is None:
        return ClaimResult(ClaimStatus.INVALID_LINK)
    if owner.telegram_id == telegram_id:
        return ClaimResult(ClaimStatus.ALREADY_YOURS, subscription)
    if owner.telegram_id > 0:
        # Someone else's real account. A link can leak — a takeover must not
        # follow from that.
        return ClaimResult(ClaimStatus.OTHER_TELEGRAM_OWNER, subscription)

    claimant = await repo.get_or_create_user(telegram_id, username)
    subscription.user_id = claimant.id
    await session.commit()
    await session.refresh(subscription)
    return ClaimResult(ClaimStatus.CLAIMED, subscription)


async def attach_telegram_to_web_account(
    session: AsyncSession,
    *,
    web_telegram_id: int,
    telegram_id: int,
    username: str | None,
) -> int:
    """Merge a website account into the Telegram account of the same person.

    The mirror image of :func:`claim_subscription_by_link`, for someone who is
    already signed into the cabinet: the session proves they hold the website
    account, the Telegram login proves they hold the chat, and holding both at
    once is what authorises joining them.

    Only a website account can be absorbed — its id is negative, marking a row
    with no chat behind it. Two real Telegram accounts are never merged: that
    would need a decision about which history survives, and nobody has asked
    for it.

    Subscriptions move; past payments stay where they were recorded. Nothing
    reads a payment through its owner after the fact, and rewriting settled
    financial rows to tidy up a profile is not a trade worth making.

    Returns the telegram_id the caller should put in the session.
    """

    if web_telegram_id >= 0 or telegram_id <= 0:
        return telegram_id

    repo = Repository(session)
    web_user = await repo.get_user_by_telegram_id(web_telegram_id)
    if web_user is None:
        return telegram_id

    owner = await repo.get_or_create_user(telegram_id, username)
    if owner.id == web_user.id:  # pragma: no cover - ids differ by sign
        return telegram_id

    await session.execute(
        update(Subscription)
        .where(Subscription.user_id == web_user.id)
        .values(user_id=owner.id)
    )
    # Carry the address over only into an empty field: the Telegram account may
    # already have one, and a receipt must keep going where the buyer expects.
    fields = {}
    if web_user.email and not owner.email:
        fields["email"] = web_user.email
    if web_user.web_password_hash and not owner.web_password_hash:
        fields["web_password_hash"] = web_user.web_password_hash
    if fields:
        await repo.update_user(owner.id, **fields)
    await session.commit()
    return owner.telegram_id
