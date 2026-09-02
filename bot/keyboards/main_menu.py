from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.texts import format_msk, trial_days
from services.payment import PLANS


DURATION_EMOJI = {30: "🚀", 90: "💎", 180: "👑", 365: "🏆"}


def main_menu_keyboard(has_subscription: bool = False, trial_available: bool = False) -> InlineKeyboardMarkup:
    """Single compact main menu shown after /start. Promo entry and help live
    in the quick-access command menu (/promo, /help)."""
    rows: list[list[InlineKeyboardButton]] = []
    if trial_available:
        rows.append(
            [InlineKeyboardButton(text=f"🎁 Активировать пробный период — {trial_days()}", callback_data="activate_trial")]
        )
    rows.append([InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_menu")])
    if has_subscription:
        rows.append(
            [
                InlineKeyboardButton(text="📋 Мои подписки", callback_data="my_subs"),
                InlineKeyboardButton(text="🔄 Продлить", callback_data="renew_menu"),
            ]
        )
    help_row = [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    if has_subscription:
        help_row.append(InlineKeyboardButton(text="💬 Отзыв", callback_data="leave_review"))
    rows.append(help_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tier_plans_keyboard(tier: str) -> InlineKeyboardMarkup:
    plan_rows = [
        [
            InlineKeyboardButton(
                text=f"{DURATION_EMOJI.get(int(plan['days']), '⏱')} {plan['label']} — {plan['rub_amount']}₽",
                callback_data=f"buy:{code}",
            )
        ]
        for code, plan in PLANS.items()
        if code.startswith(tier)
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *plan_rows,
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def renew_menu_keyboard(subscriptions) -> InlineKeyboardMarkup:
    """Pick which active subscription to renew.

    Only reached when there is more than one — with a single subscription the
    caller goes straight to the durations. Labelled by expiry, because tier
    stopped telling them apart when Premium went: two subscriptions both read
    «Продлить Обычный» and the buttons were indistinguishable.
    """
    rows = []
    for sub in subscriptions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔄 До {format_msk(sub.expires_at)}",
                    callback_data=f"renew_sub:{sub.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_durations_keyboard(tier: str, *, back_callback: str = "main_menu") -> InlineKeyboardMarkup:
    """Duration options for renewing a subscription of this tier.

    Took a `region` too while Premium existed, and pinned it into a
    `buy_region:` callback. Premium went, the call site dropped the argument,
    and the parameter stayed required — so every «Продлить» raised TypeError.
    Nothing has handled `buy_region:` since either.

    ``back_callback`` exists because this screen is now reached two ways. When
    it was entered directly (the usual case: one subscription), «Назад» must
    leave for the menu — pointing it at the picker would bounce the user
    straight back here.
    """
    rows = []
    for code, plan in PLANS.items():
        if not code.startswith(tier):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{DURATION_EMOJI.get(int(plan['days']), '⏱')} {plan['label']} — {plan['rub_amount']}₽",
                    callback_data=f"buy:{code}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)




def my_subs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Подключить устройство", callback_data="connect_device")],
            [InlineKeyboardButton(text="🔄 Продлить", callback_data="renew_menu")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def help_keyboard(support_contact: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Поддержка", url=f"https://t.me/{support_contact.lstrip('@')}")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )
