"""Кнопки с экрана-картинки открывают свой экран, а не падают.

21.09.2026 бот слал владельцу «TelegramBadRequest: there is no text in the
message to edit»: главное меню после /start приходит картинкой с подписью, а
кнопка правила его как текст. Человек нажимал — и ничего не происходило.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import promo
from bot.handlers.link import PROMPT, LinkInput, link_enter_handler


def _callback(*, photo):
    message = SimpleNamespace(
        photo=photo,
        edit_text=AsyncMock(),
        delete=AsyncMock(),
        answer=AsyncMock(),
    )
    return SimpleNamespace(message=message, answer=AsyncMock())


@pytest.mark.asyncio
async def test_the_button_on_a_banner_replaces_it_with_the_prompt():
    callback = _callback(photo=[object()])
    state = SimpleNamespace(set_state=AsyncMock())

    await link_enter_handler(callback, state)

    callback.message.edit_text.assert_not_awaited()
    callback.message.delete.assert_awaited_once()
    assert callback.message.answer.await_args.args[0] == PROMPT
    state.set_state.assert_awaited_once_with(LinkInput.subscription)
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_button_on_a_text_screen_edits_it_in_place():
    callback = _callback(photo=None)
    state = SimpleNamespace(set_state=AsyncMock())

    await link_enter_handler(callback, state)

    assert callback.message.edit_text.await_args.args[0] == PROMPT
    callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_old_promo_button_on_a_banner_opens_the_prompt():
    callback = _callback(photo=[object()])
    state = SimpleNamespace(set_state=AsyncMock())

    await promo.promo_enter_handler(callback, state)

    callback.message.edit_text.assert_not_awaited()
    assert callback.message.answer.await_args.args[0] == promo.PROMPT
