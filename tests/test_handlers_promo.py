"""Promo redemption in the bot.

Redemption used to hang off the wallet screen. When the wallet went, the only
way in went with it, so these cover the entrance as much as the redemption:
a code nobody can reach is the same as no code at all.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import promo as promo_handlers
from database.repository import Repository
from services import billing_api, promo as promo_service


class _State:
    def __init__(self):
        self.state = None
        self.cleared = False

    async def set_state(self, value):
        self.state = value

    async def clear(self):
        self.cleared = True


@pytest.mark.integration
async def test_promo_command_opens_the_prompt_without_the_wallet():
    message = SimpleNamespace(answer=AsyncMock())
    state = _State()

    await promo_handlers.promo_command(message, state)

    assert state.state == promo_handlers.PromoInput.code
    assert "Промокод" in message.answer.await_args.args[0]


@pytest.mark.integration
async def test_promo_button_still_works_for_keyboards_that_carry_it():
    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(data="promo_enter", message=message, answer=AsyncMock())
    state = _State()

    await promo_handlers.promo_enter_handler(callback, state)

    assert state.state == promo_handlers.PromoInput.code
    message.edit_text.assert_awaited_once()


@pytest.mark.integration
async def test_a_valid_code_hands_over_the_days_it_promises(session_pool, monkeypatch):
    monkeypatch.setattr(billing_api, "activate_access", AsyncMock())
    async with session_pool() as session:
        repo = Repository(session)
        await repo.create_user(telegram_id=9301, username="promo")
        await repo.create_promo_code(
            code="FREEMONTH", kind=promo_service.PROMO_SUBSCRIPTION_GRANT, value=30
        )
        await session.commit()

    message = SimpleNamespace(
        text="freemonth",
        from_user=SimpleNamespace(id=9301, username="promo"),
        answer=AsyncMock(),
    )
    state = _State()

    await promo_handlers.promo_code_message_handler(message, state, session_pool)

    assert state.cleared is True
    assert "30 дней" in message.answer.await_args.args[0]


@pytest.mark.integration
async def test_each_refusal_says_what_actually_went_wrong(session_pool, monkeypatch):
    """"Промокод не подошёл" to a code the user already spent sends them to
    support instead of telling them the answer."""
    monkeypatch.setattr(billing_api, "activate_access", AsyncMock())
    async with session_pool() as session:
        repo = Repository(session)
        await repo.create_user(telegram_id=9302, username="twice")
        await repo.create_promo_code(
            code="ONEUSE", kind=promo_service.PROMO_SUBSCRIPTION_GRANT, value=30, per_user_limit=1
        )
        await session.commit()

    def _message(text):
        return SimpleNamespace(
            text=text,
            from_user=SimpleNamespace(id=9302, username="twice"),
            answer=AsyncMock(),
        )

    first = _message("ONEUSE")
    await promo_handlers.promo_code_message_handler(first, _State(), session_pool)

    again = _message("ONEUSE")
    await promo_handlers.promo_code_message_handler(again, _State(), session_pool)
    assert "уже использовали" in again.answer.await_args.args[0]

    missing = _message("NOSUCHCODE")
    await promo_handlers.promo_code_message_handler(missing, _State(), session_pool)
    assert "Такого промокода нет" in missing.answer.await_args.args[0]


@pytest.mark.integration
async def test_an_empty_message_is_not_treated_as_a_code(session_pool):
    async with session_pool() as session:
        await Repository(session).create_user(telegram_id=9303, username="blank")

    message = SimpleNamespace(
        text="   ",
        from_user=SimpleNamespace(id=9303, username="blank"),
        answer=AsyncMock(),
    )

    await promo_handlers.promo_code_message_handler(message, _State(), session_pool)

    assert "Отправьте промокод" in message.answer.await_args.args[0]
