import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq
from config import settings
from services.alerts import send_alert

router = Router()


class SupportForm(StatesGroup):
    waiting_message = State()


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать в поддержку", callback_data="support_write")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery) -> None:
    text = (
        "🆘 <b>Поддержка</b>\n\n"
        + bq(
            f"💬 Контакт: {settings.support_contact}",
            f"🆔 Ваш ID: <code>{callback.from_user.id}</code>",
        )
        + "\n\nНажмите «Написать в поддержку» и опишите проблему — мы ответим."
    )
    await show_screen(callback, text, _support_keyboard())
    await callback.answer()


@router.callback_query(F.data == "support_write")
async def support_write_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SupportForm.waiting_message)
    if callback.message:
        await callback.message.answer(
            "✍️ Напишите ваше сообщение одним сообщением — оно уйдёт в поддержку.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="support_cancel")]]
            ),
        )
    await callback.answer()


@router.callback_query(F.data == "support_cancel")
async def support_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.answer("Отменено.", reply_markup=back_to_menu_keyboard())


@router.message(SupportForm.waiting_message)
async def support_receive(message: Message, state: FSMContext) -> None:
    body = (message.text or message.caption or "").strip()
    if not body:
        await message.answer("Пожалуйста, опишите проблему текстом.")
        return
    if body.startswith("/"):
        await state.clear()
        await message.answer("Отменено.", reply_markup=back_to_menu_keyboard())
        return

    await state.clear()
    user = message.from_user
    uname = f"@{user.username}" if user and user.username else "—"
    name = html.escape(user.full_name) if user and user.full_name else "—"
    alert = (
        "🆘 <b>Обращение в поддержку</b>\n"
        f"От: {name} ({uname})\n"
        f"ID: <code>{user.id if user else '—'}</code>\n\n"
        f"{html.escape(body)}"
    )
    sent = await send_alert(alert)
    if sent:
        await message.answer(
            "✅ Сообщение отправлено в поддержку. Мы ответим в ближайшее время.",
            reply_markup=back_to_menu_keyboard(),
        )
    else:
        await message.answer(
            f"Не удалось отправить автоматически. Напишите напрямую: {settings.support_contact}",
            reply_markup=back_to_menu_keyboard(),
        )
