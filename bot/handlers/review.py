"""User reviews: /отзыв command and a menu button. Collects a rating + text,
stores it, and pings the owner (via the alerts bot) with who wrote it so a
detailed review can be rewarded."""
from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from database.repository import Repository
from services.alerts import send_alert

logger = logging.getLogger(__name__)
router = Router()

# A review this long or longer counts as "detailed" and is flagged for a gift.
DETAILED_REVIEW_CHARS = 120
MAX_REVIEW_CHARS = 2000

_PROMPT = (
    "💬 <b>Оставьте отзыв</b>\n\n"
    "Поставьте оценку, а затем напишите пару слов о сервисе. "
    "За подробный отзыв дарим бонус 🎁"
)


class ReviewInput(StatesGroup):
    text = State()


def _rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐" * n, callback_data=f"review_rate:{n}") for n in (1, 2, 3)],
            [InlineKeyboardButton(text="⭐" * n, callback_data=f"review_rate:{n}") for n in (4, 5)],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


async def _open_review(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_PROMPT, reply_markup=_rating_keyboard())


@router.message(Command("отзыв", "review", "feedback"))
async def review_command(message: Message, state: FSMContext) -> None:
    await _open_review(message, state)


@router.callback_query(F.data == "leave_review")
async def review_button(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message:
        await _open_review(callback.message, state)


@router.callback_query(F.data.startswith("review_rate:"))
async def review_rate(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        rating = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    rating = max(1, min(5, rating))
    await state.update_data(rating=rating)
    await state.set_state(ReviewInput.text)
    if callback.message:
        await callback.message.answer(
            f"Оценка {'⭐' * rating}. Теперь напишите отзыв одним сообщением 👇"
        )


@router.message(ReviewInput.text, F.text)
async def review_text(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    await state.clear()
    rating = int(data.get("rating", 5))
    text = (message.text or "").strip()[:MAX_REVIEW_CHARS]
    if not text:
        await message.answer("Пустой отзыв. Нажмите /отзыв, чтобы попробовать снова.")
        return

    detailed = len(text) >= DETAILED_REVIEW_CHARS
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(message.from_user.id)
        if user is None:
            await message.answer("Не нашёл вас в базе. Нажмите /start и попробуйте снова.")
            return
        await repo.create_review(user_id=user.id, rating=rating, text=text)

    handle = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    await send_alert(
        f"💬 <b>Новый отзыв</b> {'⭐' * rating}\n"
        f"От: {html.escape(handle)} (tg <code>{message.from_user.id}</code>, user #{user.id})\n"
        + ("🎁 <b>подробный — можно наградить</b>\n" if detailed else "")
        + f"\n{html.escape(text)}"
    )

    thanks = "Спасибо за отзыв! 🙏"
    if detailed:
        thanks += "\nМы свяжемся с вами по бонусу за подробный отзыв 🎁"
    await message.answer(thanks, reply_markup=back_to_menu_keyboard())
