"""Attach a subscription bought on the website to this Telegram account.

A website purchase without a Telegram login lands on its own account under a
synthetic negative id, so the buyer opens the bot, sees nothing, and concludes
the money vanished. Two of the first three support tickets we looked at were
exactly that.

Proof of ownership is the subscription link, the same standard the renewal path
already uses: it carries a credential the panel signed, and it is the one thing
the customer holds without being able to open anything else. An email address
would not do — it is public, and accepting one would hand over the subscription
of anyone whose address can be guessed.

The claim itself lives in ``services.account_link``; this module is the doorway.
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.texts import format_msk
from services.account_link import ClaimStatus, claim_subscription_by_link
from services.tariffs import resolve_tariff

logger = logging.getLogger(__name__)
router = Router()

PROMPT = (
    "🔗 <b>Привязать подписку</b>\n\n"
    "Купили на сайте, а здесь её не видно? Пришлите ссылку вашей подписки "
    "одним сообщением — она есть в приложении и в письме о выдаче.\n\n"
    "Выглядит так:\n"
    "<code>https://sub.unlockvpn.site/sub/…</code>"
)

_ERRORS = {
    ClaimStatus.INVALID_LINK: (
        "Ссылка не подошла. Проверьте, что скопировали её целиком, "
        "и пришлите ещё раз."
    ),
    ClaimStatus.OTHER_TELEGRAM_OWNER: (
        "Эта подписка уже привязана к другому аккаунту Telegram. "
        "Если это ваш аккаунт — напишите в поддержку, разберёмся."
    ),
}


class LinkInput(StatesGroup):
    subscription = State()


def _plan_title(plan: str) -> str:
    try:
        return resolve_tariff(plan).title
    except ValueError:
        return plan


@router.callback_query(F.data == "link_subscription")
async def link_enter_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LinkInput.subscription)
    if callback.message is not None:
        await callback.message.edit_text(PROMPT, reply_markup=back_to_menu_keyboard())
    await callback.answer()


@router.message(Command("link"))
async def link_command(message: Message, state: FSMContext) -> None:
    await state.set_state(LinkInput.subscription)
    await message.answer(PROMPT, reply_markup=back_to_menu_keyboard())


@router.message(LinkInput.subscription)
async def link_message_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    link = (message.text or "").strip()
    if not link:
        await message.answer(
            "Пришлите ссылку текстом или вернитесь в меню.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    async with session_pool() as session:
        result = await claim_subscription_by_link(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            link=link,
        )

    if result.status is ClaimStatus.ALREADY_YOURS:
        await state.clear()
        await message.answer(
            "Эта подписка уже привязана к вашему аккаунту — она в «📋 Мои подписки».",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    if result.status is not ClaimStatus.CLAIMED:
        # The state stays set so a corrected link can be sent straight away.
        await message.answer(_ERRORS[result.status], reply_markup=back_to_menu_keyboard())
        return

    await state.clear()
    subscription = result.subscription
    assert subscription is not None  # CLAIMED always carries one
    logger.info(
        "Subscription %s claimed by telegram_id=%s",
        subscription.id,
        message.from_user.id,
    )
    await message.answer(
        "✅ <b>Подписка привязана</b>\n\n"
        f"Тариф: {_plan_title(subscription.plan)}\n"
        f"Действует до: {format_msk(subscription.expires_at)}\n\n"
        "Теперь она видна в «📋 Мои подписки». Переподключать ничего не нужно — "
        "ссылка в приложении осталась прежней.",
        reply_markup=back_to_menu_keyboard(),
    )
