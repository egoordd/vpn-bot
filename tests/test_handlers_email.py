from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import email_settings
from database.repository import Repository


def _callback(data: str, telegram_id: int = 970):
    message = SimpleNamespace(
        edit_text=AsyncMock(),
        answer=AsyncMock(),
    )
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=telegram_id, username="emailuser"),
        message=message,
        answer=AsyncMock(),
    )


def _message(text: str, telegram_id: int = 970):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=telegram_id, username="emailuser"),
        answer=AsyncMock(),
    )


def _state(data: dict | None = None):
    return SimpleNamespace(
        clear=AsyncMock(),
        set_state=AsyncMock(),
        get_data=AsyncMock(return_value=data or {}),
        update_data=AsyncMock(),
    )


@pytest.mark.integration
async def test_email_menu_shows_current_email(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=971, username="emailuser")
        await repo.update_user(user.id, email="old@mail.ru")

    callback = _callback("email_menu", telegram_id=971)
    await email_settings.email_menu_handler(callback, _state(), session_pool)

    text = callback.message.edit_text.await_args.args[0]
    assert "old@mail.ru" in text
    callback.answer.assert_awaited_once()


@pytest.mark.integration
async def test_email_menu_without_email(session_pool):
    callback = _callback("email_menu", telegram_id=972)
    await email_settings.email_menu_handler(callback, _state(), session_pool)

    text = callback.message.edit_text.await_args.args[0]
    assert "не указан" in text


@pytest.mark.integration
async def test_email_input_saves_normalized_address(session_pool):
    message = _message("  New@Mail.RU ", telegram_id=973)
    state = _state()

    await email_settings.email_input_handler(message, state, session_pool)

    state.clear.assert_awaited_once()
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(973)
        assert user.email == "new@mail.ru"
    reply = message.answer.await_args.args[0]
    assert "сохранён" in reply


@pytest.mark.integration
async def test_email_input_rejects_invalid(session_pool):
    message = _message("not-an-email", telegram_id=974)
    state = _state()

    await email_settings.email_input_handler(message, state, session_pool)

    state.clear.assert_not_awaited()
    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(974)
        assert user is None or user.email is None


@pytest.mark.integration
async def test_email_input_overwrites_existing(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=975, username="emailuser")
        await repo.update_user(user.id, email="old@mail.ru")

    await email_settings.email_input_handler(_message("fresh@mail.ru", telegram_id=975), _state(), session_pool)

    async with session_pool() as session:
        user = await Repository(session).get_user_by_telegram_id(975)
        assert user.email == "fresh@mail.ru"
