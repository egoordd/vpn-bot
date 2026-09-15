"""Статистика зеркала — только его собственные аккаунты.

Зеркало ведёт аккаунты в отдельном диапазоне ID (``mirror_account_id``): всё, что
человек начал или купил в зеркале, записано под −(9·10¹⁵ + telegram_id). Общую
картину по базе показывает /stats основного бота; здесь — ровно зеркало, иначе
его цифры тонут в основном потоке и по ним нельзя понять, работает ли оно.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import bq
from database.models import FunnelEvent, Payment, Subscription, User
from services.tariffs import resolve_tariff

TRIAL_PLAN = "trial"
FUNNEL_STEPS: tuple[tuple[str, str], ...] = (
    ("start", "Запустили бота"),
    ("trial", "Получили пробный период"),
    ("first_connect", "Подключились"),
    ("payment", "Оплатили"),
)


@dataclass(frozen=True)
class MirrorStats:
    users_total: int = 0
    users_day: int = 0
    users_week: int = 0
    trials_total: int = 0
    trials_active: int = 0
    paid_active: int = 0
    paid_by_plan: dict[str, int] = field(default_factory=dict)
    payments_total: int = 0
    payments_week: int = 0
    revenue_total_rub: int = 0
    revenue_week_rub: int = 0
    invoices_open: int = 0
    funnel: dict[str, int] = field(default_factory=dict)


async def collect(
    session: AsyncSession, *, account_ceiling: int, now: datetime | None = None
) -> MirrorStats:
    """Цифры по аккаунтам с ``telegram_id <= account_ceiling`` — это и есть зеркало.

    Оплаты считаются по аккаунту, а не по платёжке: деньги от человека из зеркала
    должны попасть в сводку, каким бы способом он ни заплатил.
    """

    now = now or datetime.now(timezone.utc)
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    mirror_users = User.telegram_id <= account_ceiling

    async def scalar(query) -> int:
        return int((await session.execute(query)).scalar_one() or 0)

    users = select(func.count(User.id)).where(mirror_users)
    subs = select(func.count(Subscription.id)).join(User).where(mirror_users)
    live = (Subscription.is_active.is_(True), Subscription.expires_at > now)
    completed = (
        select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0))
        .join(User)
        .where(mirror_users, Payment.status == "completed")
    )

    paid_rows = await session.execute(
        select(Subscription.plan, func.count(Subscription.id))
        .join(User)
        .where(mirror_users, Subscription.plan != TRIAL_PLAN, *live)
        .group_by(Subscription.plan)
    )
    paid_by_plan = {plan: int(count) for plan, count in paid_rows.all()}

    total_count, total_kopecks = (await session.execute(completed)).one()
    week_count, week_kopecks = (
        await session.execute(completed.where(Payment.created_at >= week))
    ).one()

    funnel_rows = await session.execute(
        select(FunnelEvent.event, func.count(FunnelEvent.user_id.distinct()))
        .join(User, User.id == FunnelEvent.user_id)
        .where(mirror_users)
        .group_by(FunnelEvent.event)
    )

    return MirrorStats(
        users_total=await scalar(users),
        users_day=await scalar(users.where(User.created_at >= day)),
        users_week=await scalar(users.where(User.created_at >= week)),
        trials_total=await scalar(subs.where(Subscription.plan == TRIAL_PLAN)),
        trials_active=await scalar(subs.where(Subscription.plan == TRIAL_PLAN, *live)),
        paid_active=sum(paid_by_plan.values()),
        paid_by_plan=paid_by_plan,
        payments_total=int(total_count),
        payments_week=int(week_count),
        revenue_total_rub=int(total_kopecks) // 100,
        revenue_week_rub=int(week_kopecks) // 100,
        invoices_open=await scalar(
            select(func.count(Payment.id)).join(User).where(mirror_users, Payment.status == "pending")
        ),
        funnel={event: int(count) for event, count in funnel_rows.all()},
    )


def _plan_title(plan: str) -> str:
    try:
        return resolve_tariff(plan).title
    except ValueError:
        return plan


def _rub(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


def _funnel_lines(funnel: dict[str, int]) -> list[str]:
    lines: list[str] = []
    previous: int | None = None
    for event, label in FUNNEL_STEPS:
        count = funnel.get(event, 0)
        if previous:
            lines.append(f"{label}: {count} ({count * 100 // previous}% от пред.)")
        else:
            lines.append(f"{label}: {count}")
        previous = count
    return lines


def render(stats: MirrorStats) -> str:
    plans = ", ".join(
        f"{html.escape(_plan_title(plan))}: {count}" for plan, count in sorted(stats.paid_by_plan.items())
    ) or "нет"
    return (
        "📊 <b>Статистика зеркала</b>\n\n"
        "👥 <b>Пользователи</b>\n"
        + bq(
            f"Всего: {stats.users_total}",
            f"Новых за 24ч: {stats.users_day}",
            f"Новых за 7д: {stats.users_week}",
        )
        + "\n\n🎁 <b>Пробный период</b>\n"
        + bq(f"Выдано: {stats.trials_total}", f"Действует сейчас: {stats.trials_active}")
        + "\n\n🔑 <b>Платные подписки</b>\n"
        + bq(f"Активных: {stats.paid_active}", f"По тарифам: {plans}")
        + "\n\n💳 <b>Оплаты</b>\n"
        + bq(
            f"Всего: {stats.payments_total} на {_rub(stats.revenue_total_rub)}",
            f"За 7д: {stats.payments_week} на {_rub(stats.revenue_week_rub)}",
            f"Открытых счетов: {stats.invoices_open}",
        )
        + "\n\n🧭 <b>Воронка</b>\n"
        + bq(*_funnel_lines(stats.funnel))
    )
