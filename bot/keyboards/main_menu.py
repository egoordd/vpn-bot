from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.payment import PLANS
from services.tariffs import PREMIUM_REGIONS


DURATION_EMOJI = {30: "🚀", 90: "💎", 180: "👑", 365: "🏆"}


def _min_price(tier: str) -> int:
    """Cheapest actual plan price for a tier (the real entry cost, not a
    per-month figure that the user can never pay in one go)."""
    return min(
        int(plan["rub_amount"])
        for code, plan in PLANS.items()
        if code.startswith(tier)
    )


def _tier_buttons() -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=f"🚀 Обычный — от {_min_price('standard')}₽",
                callback_data="buy_tier:standard",
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Premium (скоро)",
                callback_data="buy_tier:premium",
            )
        ],
    ]


def landing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *_tier_buttons(),
            [
                InlineKeyboardButton(text="💰 Кошелёк", callback_data="wallet"),
                InlineKeyboardButton(text="👥 Пригласить", callback_data="referral"),
            ],
            [
                InlineKeyboardButton(text="❓ Поддержка", callback_data="support"),
                InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions"),
            ],
        ]
    )


def tier_select_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *_tier_buttons(),
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


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
            [InlineKeyboardButton(text="◀️ Назад", callback_data="buy_menu")],
        ]
    )


def renew_menu_keyboard(subscriptions) -> InlineKeyboardMarkup:
    """Pick which active subscription to renew."""
    rows = []
    for sub in subscriptions:
        label = "💎 Premium" if sub.tier == "premium" else "🌐 Обычный"
        rows.append([InlineKeyboardButton(text=f"🔄 Продлить {label}", callback_data=f"renew_sub:{sub.id}")])
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def renew_durations_keyboard(tier: str, region: str | None) -> InlineKeyboardMarkup:
    """Duration options for renewing a specific tier; premium keeps its region."""
    rows = []
    for code, plan in PLANS.items():
        if not code.startswith(tier):
            continue
        if tier == "premium" and region:
            callback = f"buy_region:{code}:{region}"
        else:
            callback = f"buy:{code}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{DURATION_EMOJI.get(int(plan['days']), '⏱')} {plan['label']} — {plan['rub_amount']}₽",
                    callback_data=callback,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="renew_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_location_keyboard(plan: str) -> InlineKeyboardMarkup:
    region_rows = [
        [
            InlineKeyboardButton(
                text=f"{region.flag} {region.title}",
                callback_data=f"buy_region:{plan}:{code}",
            )
        ]
        for code, region in PREMIUM_REGIONS.items()
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *region_rows,
            [InlineKeyboardButton(text="◀️ Назад", callback_data="buy_menu")],
        ]
    )


def active_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Подключить устройство", callback_data="connect_device")],
            [InlineKeyboardButton(text="🌍 Локации", callback_data="locations")],
            [
                InlineKeyboardButton(text="🛒 Купить тариф", callback_data="buy_menu"),
                InlineKeyboardButton(text="🔄 Продлить", callback_data="renew_menu"),
            ],
            [
                InlineKeyboardButton(text="💰 Кошелёк", callback_data="wallet"),
                InlineKeyboardButton(text="👥 Пригласить", callback_data="referral"),
            ],
            [InlineKeyboardButton(text="❓ Поддержка", callback_data="support")],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Пополнить", callback_data="topup_menu")],
            [InlineKeyboardButton(text="🎟 Промокод", callback_data="promo_enter")],
            [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="referral")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def topup_keyboard(presets_kopecks: tuple[int, ...]) -> InlineKeyboardMarkup:
    preset_rows = [
        [
            InlineKeyboardButton(
                text=f"➕ {kopecks // 100}₽",
                callback_data=f"topup:{kopecks}",
            )
        ]
        for kopecks in presets_kopecks
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *preset_rows,
            [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="topup_custom")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="wallet")],
        ]
    )


def back_to_wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К кошельку", callback_data="wallet")],
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return landing_keyboard()
