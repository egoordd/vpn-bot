from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.texts import format_msk, trial_days
from config import settings
from services import subscription_slots as slots
from services.payment import PLANS


# Цвет кнопки Telegram понимает с Bot API: "primary" — синяя, "success" — зелёная,
# "danger" — красная. Красим ровно одно главное действие на экран: когда цветные
# все, цвет перестаёт что-либо значить и экран становится пёстрым.
DURATION_EMOJI = {30: "🚀", 90: "💎", 180: "👑", 365: "🏆"}


def main_menu_keyboard(
    has_subscription: bool = False,
    trial_available: bool = False,
    can_add_subscription: bool = False,
) -> InlineKeyboardMarkup:
    """Single compact main menu shown after /start. Promo entry and help live
    in the quick-access command menu (/promo, /help)."""
    rows: list[list[InlineKeyboardButton]] = []
    if trial_available:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🎁 Активировать пробный период — {trial_days()}",
                    callback_data="activate_trial",
                    style="success",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_menu", style="primary")]
    )
    if has_subscription and can_add_subscription:
        # Отдельная ссылка и свои устройства — например, для семьи. Обычная
        # «Купить» по-прежнему продлевает основную подписку.
        rows.append([InlineKeyboardButton(text="➕ Ещё одна подписка", callback_data="buy_extra")])
    if not has_subscription:
        # Shown only to an empty account, which is exactly what a website buyer
        # sees when their purchase landed on a separate email-only user. Anyone
        # with a subscription never meets this button.
        rows.append(
            [InlineKeyboardButton(text="🔗 Уже купил на сайте", callback_data="link_subscription")]
        )
    if has_subscription:
        rows.append(
            [
                InlineKeyboardButton(text="📋 Мои подписки", callback_data="my_subs"),
                InlineKeyboardButton(text="🔄 Продлить", callback_data="renew_menu"),
            ]
        )
    help_row = [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    if settings.news_channel_url:
        help_row.append(InlineKeyboardButton(text="📣 Новости", url=settings.news_channel_url))
    if has_subscription:
        help_row.append(InlineKeyboardButton(text="💬 Отзыв", callback_data="leave_review"))
    rows.append(help_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tier_plans_keyboard(tier: str, target: str | None = None) -> InlineKeyboardMarkup:
    plan_rows = [
        [
            InlineKeyboardButton(
                text=f"{DURATION_EMOJI.get(int(plan['days']), '⏱')} {plan['label']} — {plan['rub_amount']}₽",
                callback_data=f"buy:{slots.with_target(code, target)}",
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
    caller goes straight to the durations. Labelled by expiry so two historical
    active rows are never indistinguishable.
    """
    rows = []
    for sub in subscriptions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔄 {slots.label(sub)} · до {format_msk(sub.expires_at)}",
                    callback_data=f"renew_sub:{sub.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_durations_keyboard(
    tier: str, *, back_callback: str = "main_menu", target: str | None = None
) -> InlineKeyboardMarkup:
    """Duration options for renewing a subscription of this tier.

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
                    callback_data=f"buy:{slots.with_target(code, target)}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)




def my_subs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Подключить устройство", callback_data="connect_device", style="primary"
                )
            ],
            [InlineKeyboardButton(text="🔄 Продлить", callback_data="renew_menu", style="success")],
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
    rows = [
        [InlineKeyboardButton(text="💬 Поддержка", url=f"https://t.me/{support_contact.lstrip('@')}")],
    ]
    # Someone reading the help screen is already stuck; the channel is where the
    # working address is posted when a domain stops opening.
    if settings.news_channel_url:
        rows.append(
            [InlineKeyboardButton(text="📣 Новости и статус", url=settings.news_channel_url)]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
