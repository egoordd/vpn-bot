"""Screen navigation: redrawing a screen must not be able to kill a handler."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot import navigation

NOT_MODIFIED = (
    "Telegram server says - Bad Request: message is not modified: specified new "
    "message content and reply markup are exactly the same as a current content "
    "and reply markup of the message"
)


def _callback(message):
    return SimpleNamespace(message=message)


@pytest.mark.unit
async def test_redrawing_the_same_screen_is_not_an_error():
    """Tapping the button for the screen you are already on asks Telegram to
    replace a message with itself, which it refuses. The user sees exactly what
    they asked for, so the handler must carry on — before this, it died mid-flow
    and the owner got an error alert for a no-op."""
    message = SimpleNamespace(
        photo=None,
        edit_text=AsyncMock(side_effect=TelegramBadRequest(method=None, message=NOT_MODIFIED)),
    )
    await navigation.show_screen(_callback(message), "same text")
    message.edit_text.assert_awaited_once()


@pytest.mark.unit
async def test_a_real_telegram_failure_still_propagates():
    """Swallowing every BadRequest would hide genuinely broken screens — a
    message too long, unparseable markup, a deleted chat."""
    message = SimpleNamespace(
        photo=None,
        edit_text=AsyncMock(
            side_effect=TelegramBadRequest(
                method=None, message="Telegram server says - Bad Request: message is too long"
            )
        ),
    )
    with pytest.raises(TelegramBadRequest):
        await navigation.show_screen(_callback(message), "x" * 5000)


@pytest.mark.unit
async def test_a_photo_screen_is_replaced_rather_than_edited():
    """Editing only the caption would leave the image stuck above the new text."""
    message = SimpleNamespace(
        photo=[object()],
        delete=AsyncMock(),
        answer=AsyncMock(),
        edit_text=AsyncMock(),
    )
    await navigation.show_screen(_callback(message), "text")
    message.delete.assert_awaited_once()
    message.answer.assert_awaited_once()
    message.edit_text.assert_not_awaited()
