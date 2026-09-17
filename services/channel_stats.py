"""/channels — сводка /stats, разложенная на бот, сайт и зеркало.

Все три входа пишут в одну базу, а различаются диапазоном ``telegram_id``:
- бот — настоящие Telegram ID (положительные);
- сайт — покупатели по почте, синтетический отрицательный ID;
- зеркало — свой диапазон ``mirror_account_id``, ниже MIRROR_CEILING.

Кто на сайте вошёл через Telegram, получает обычный Telegram-аккаунт — от
ботового он ничем не отличается и попадает в «Бот». Аккаунты считаются вместе
с незавершёнными покупками на сайте: оформление создаёт аккаунт до оплаты.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import bq
from database.models import Payment, Subscription, User

# mirror_account_id(0): тот же порог, что у зеркала (сверяется тестом, чтобы не
# тянуть сюда весь services.mirror_bot).
MIRROR_CEILING = -9_000_000_000_000_000
TRIAL_PLAN = "trial"

CHANNELS: tuple[tuple[str, str], ...] = (
    ("bot", "🤖 <b>Бот</b>"),
    ("site", "🌐 <b>Сайт</b>"),
    ("mirror", "🪞 <b>Зеркало</b>"),
)
_ACCOUNTS = {
    "bot": User.telegram_id > 0,
    "site": (User.telegram_id < 0) & (User.telegram_id > MIRROR_CEILING),
    "mirror": User.telegram_id <= MIRROR_CEILING,
}


@dataclass(frozen=True)
class ChannelStats:
    users_total: int = 0
    users_day: int = 0
    users_week: int = 0
    trials_active: int = 0
    paid_active: int = 0
    payments_total: int = 0
    payments_week: int = 0
    revenue_total_rub: int = 0
    revenue_week_rub: int = 0

    def __add__(self, other: ChannelStats) -> ChannelStats:
        return ChannelStats(
            **{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)}
        )


async def _collect_one(session: AsyncSession, accounts, now: datetime) -> ChannelStats:
    day, week = now - timedelta(days=1), now - timedelta(days=7)

    async def scalar(query) -> int:
        return int((await session.execute(query)).scalar_one() or 0)

    users = select(func.count(User.id)).where(accounts)
    active = (
        select(func.count(Subscription.id))
        .join(User)
        .where(accounts, Subscription.is_active.is_(True), Subscription.expires_at > now)
    )
    completed = select(func.count(Payment.id)).join(User).where(accounts, Payment.status == "completed")
    # Суммы только в рублях: старые оплаты CryptoBot лежат в центах USDT.
    kopecks = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(User)
        .where(accounts, Payment.status == "completed", func.upper(Payment.currency) == "RUB")
    )

    return ChannelStats(
        users_total=await scalar(users),
        users_day=await scalar(users.where(User.created_at >= day)),
        users_week=await scalar(users.where(User.created_at >= week)),
        trials_active=await scalar(active.where(Subscription.plan == TRIAL_PLAN)),
        paid_active=await scalar(active.where(Subscription.plan != TRIAL_PLAN)),
        payments_total=await scalar(completed),
        payments_week=await scalar(completed.where(Payment.created_at >= week)),
        revenue_total_rub=await scalar(kopecks) // 100,
        revenue_week_rub=await scalar(kopecks.where(Payment.created_at >= week)) // 100,
    )


async def collect(session: AsyncSession, *, now: datetime | None = None) -> dict[str, ChannelStats]:
    now = now or datetime.now(timezone.utc)
    return {channel: await _collect_one(session, _ACCOUNTS[channel], now) for channel, _ in CHANNELS}


def _rub(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


def _card(title: str, stats: ChannelStats) -> str:
    return f"{title}\n" + bq(
        f"Пользователей: {stats.users_total} (+{stats.users_day} за 24ч, +{stats.users_week} за 7д)",
        f"Активных подписок: {stats.trials_active + stats.paid_active} "
        f"(платных {stats.paid_active}, пробных {stats.trials_active})",
        f"Оплат: {stats.payments_total} на {_rub(stats.revenue_total_rub)} "
        f"(за 7д: {stats.payments_week} на {_rub(stats.revenue_week_rub)})",
    )


def render(stats: dict[str, ChannelStats]) -> str:
    total = sum((stats[channel] for channel, _ in CHANNELS), ChannelStats())
    cards = [_card(title, stats[channel]) for channel, title in CHANNELS]
    return (
        "🧭 <b>Бот / сайт / зеркало</b>\n\n"
        + "\n\n".join(cards)
        + "\n\n"
        + _card("Σ <b>Всего</b>", total)
        + "\n\n"
        + bq(
            "Сайт — покупатели по почте. Кто оформил на сайте через Telegram, считается в «Бот».",
            "Пользователи сайта включают незавершённые оформления: аккаунт создаётся до оплаты.",
            "Суммы — только рублёвые оплаты.",
        )
    )
