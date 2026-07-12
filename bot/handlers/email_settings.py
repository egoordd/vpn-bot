"""Email settings: view and change the receipt email (/email + inline menu).

The email is stored on the user row and reused for every card payment's
54-ФЗ чек; the same address is editable from the website cabinet.
"""
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.texts import bq
from database.repository import Repository

router = Router(name="email_settings")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailSettingsInput(StatesGroup):
    email = State()


def _menu_keyboard(has_email: bool) -> InlineKeyboardMarkup:
    label = "✏️ Изменить email" if has_email else "✏️ Указать email"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data="email_edit")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def _edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="email_menu")]]
    )


def _menu_text(email: str | None) -> str:
    current = email or "не указан"
    return (
        "📧 <b>Email для чеков</b>\n\n"
        + bq(f"Текущий: {current}")
        + "\n\nНа этот адрес приходят чеки об оплате картой. Его можно изменить в любой момент."
    )


async def _show_menu_message(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    async with session_pool() as session:
        user = await Repository(session).get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
    await message.answer(_menu_text(user.email), reply_markup=_menu_keyboard(bool(user.email)))


@router.message(Command("email"))
async def email_command_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    await _show_menu_message(message, session_pool)


@router.callback_query(F.data == "email_menu")
async def email_menu_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    async with session_pool() as session:
        user = await Repository(session).get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
    try:
        await callback.message.edit_text(
            _menu_text(user.email), reply_markup=_menu_keyboard(bool(user.email))
        )
    except Exception:
        await callback.message.answer(
            _menu_text(user.email), reply_markup=_menu_keyboard(bool(user.email))
        )
    await callback.answer()


@router.callback_query(F.data == "email_edit")
async def email_edit_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EmailSettingsInput.email)
    text = (
        "✏️ <b>Новый email</b>\n\n"
        "Отправьте адрес одним сообщением (например, <code>name@mail.ru</code>)."
    )
    try:
        await callback.message.edit_text(text, reply_markup=_edit_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=_edit_keyboard())
    await callback.answer()


@router.message(EmailSettingsInput.email)
async def email_input_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    email = (message.text or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 320:
        await message.answer(
            "Это не похоже на email. Отправьте адрес вида <code>name@mail.ru</code>.",
            reply_markup=_edit_keyboard(),
        )
        return

    await state.clear()
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        await repo.update_user(user.id, email=email)

    await message.answer(
        "✅ <b>Email сохранён</b>\n\n" + bq(f"📧 {email}"),
        reply_markup=_menu_keyboard(True),
    )
