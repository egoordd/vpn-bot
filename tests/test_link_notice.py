"""После /link владелец почты узнаёт, что его подписку с сайта привязали к Telegram.

Ссылку подписки пересылают родным, а /link переносит подписку аккаунта сайта
тому, кто её прислал. Запретить это нельзя — так покупатель с сайта находит
подписку в боте, — но владелец почты должен об этом узнать (аудит 22.09.2026, SEC-02).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services.account_link import ClaimStatus, claim_subscription_by_link
from tests.test_account_link import _link, _website_subscription


@pytest.mark.asyncio
async def test_the_claim_reports_the_site_owners_email(db_session):
    owner, _ = await _website_subscription(db_session, "tg_-556", -556)
    await Repository(db_session).update_user(owner.id, email="buyer@mail.ru")

    result = await claim_subscription_by_link(db_session, telegram_id=4243, username="kid", link=_link("tg_-556"))

    assert result.status is ClaimStatus.CLAIMED
    assert result.previous_owner_email == "buyer@mail.ru"


@pytest.mark.asyncio
async def test_the_bot_mails_the_previous_owner(db_session, session_pool, monkeypatch):
    from bot.handlers import link as handler
    from services import web_delivery

    async with session_pool() as session:
        owner, _ = await _website_subscription(session, "tg_-557", -557)
        await Repository(session).update_user(owner.id, email="buyer2@mail.ru")

    notice = AsyncMock(return_value=True)
    monkeypatch.setattr(web_delivery, "send_link_notice", notice)
    message = SimpleNamespace(
        text=_link("tg_-557"),
        from_user=SimpleNamespace(id=4244, username="kid2"),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock())

    await handler.link_message_handler(message, state, session_pool)

    notice.assert_awaited_once_with("buyer2@mail.ru", "kid2")
