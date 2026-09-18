"""/utm в зеркале — рекламные ссылки в зеркало, их переходы и результат.

То же, что /utm основного бота, но на своих таблицах: зеркало и основной бот
закупают рекламу порознь, и ссылка зеркала обязана вести в зеркало и считать
только аккаунты зеркала (``telegram_id`` ниже ``mirror_account_id(0)``).

Ссылка ``t.me/<зеркало>?start=utm_<code>``; новый человек получает
``users.source = "utm_<code>"``, и ссылке засчитываются его пробный период и
оплаты. Уже знакомым источник не ставится — иначе реклама забрала бы оплаты
старого клиента, который просто снова нажал ссылку.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from bot.texts import bq
from database.models import Base, FunnelEvent, Payment, User, utcnow
from services.utm_links import new_code, parse_start_payload, source_of, start_link

__all__ = [
    "LinkStats", "MirrorUtmLink", "MirrorUtmVisit", "collect", "create", "get",
    "parse_start_payload", "register_start", "render_created", "render_list", "source_of",
]

TITLE_MAX = 64
LIST_LIMIT = 20
# mirror_account_id(0): аккаунты зеркала лежат ниже этой границы. Число, а не
# импорт из mirror_bot — тот сам импортирует этот модуль.
MIRROR_CEILING = -9_000_000_000_000_000


class MirrorUtmLink(Base):
    """Рекламная ссылка в зеркало, выпущенная админом через /utm."""

    __tablename__ = "mirror_utm_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


class MirrorUtmVisit(Base):
    """Каждый /start по ссылке зеркала — и новичка, и уже знакомого человека."""

    __tablename__ = "mirror_utm_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    is_new_user: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True, nullable=False
    )


async def get(session: AsyncSession, code: str) -> MirrorUtmLink | None:
    return await session.scalar(select(MirrorUtmLink).where(MirrorUtmLink.code == code))


async def create(session: AsyncSession, *, title: str, created_by: int | None) -> MirrorUtmLink:
    clean = " ".join((title or "").split())[:TITLE_MAX]
    if not clean:
        raise ValueError("title_required")
    for _ in range(5):
        code = new_code()
        if await get(session, code) is None:
            break
    else:  # 36⁸ вариантов: пять совпадений подряд значат, что сломан генератор
        raise RuntimeError("could not pick a free utm code")
    link = MirrorUtmLink(code=code, title=clean, created_by=created_by)
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def register_start(session: AsyncSession, *, user: User, code: str, is_new_user: bool) -> bool:
    """Записать переход по ссылке зеркала. False — такой ссылки зеркало не выпускало."""
    if await get(session, code) is None:
        return False
    session.add(MirrorUtmVisit(code=code, user_id=user.id, is_new_user=is_new_user))
    if is_new_user and not user.source:
        user.source = source_of(code)
    await session.commit()
    return True


@dataclass(frozen=True)
class LinkStats:
    link: MirrorUtmLink
    visits: int = 0
    new_users: int = 0
    trials: int = 0
    paid_users: int = 0
    revenue_rub: int = 0


async def collect(session: AsyncSession, *, limit: int = LIST_LIMIT) -> tuple[list[LinkStats], int]:
    """Свежие ссылки зеркала со статистикой и общее число выпущенных."""
    total = int(await session.scalar(select(func.count(MirrorUtmLink.id))) or 0)
    links = (
        await session.scalars(
            select(MirrorUtmLink).order_by(MirrorUtmLink.created_at.desc(), MirrorUtmLink.id.desc()).limit(limit)
        )
    ).all()
    if not links:
        return [], total
    codes = [link.code for link in links]
    sources = [source_of(code) for code in codes]
    mirror_people = (User.source.in_(sources), User.telegram_id <= MIRROR_CEILING)

    visits = dict((await session.execute(
        select(MirrorUtmVisit.code, func.count(MirrorUtmVisit.id))
        .where(MirrorUtmVisit.code.in_(codes)).group_by(MirrorUtmVisit.code)
    )).all())
    new_users = dict((await session.execute(
        select(MirrorUtmVisit.code, func.count(MirrorUtmVisit.user_id.distinct()))
        .where(MirrorUtmVisit.code.in_(codes), MirrorUtmVisit.is_new_user.is_(True))
        .group_by(MirrorUtmVisit.code)
    )).all())
    trials = dict((await session.execute(
        select(User.source, func.count(User.id.distinct()))
        .join(FunnelEvent, FunnelEvent.user_id == User.id)
        .where(*mirror_people, FunnelEvent.event == "trial")
        .group_by(User.source)
    )).all())
    paid = {
        source: (int(buyers), int(kopecks))
        for source, buyers, kopecks in (await session.execute(
            select(User.source, func.count(User.id.distinct()), func.coalesce(func.sum(Payment.amount), 0))
            .join(Payment, Payment.user_id == User.id)
            .where(*mirror_people, Payment.status == "completed", func.upper(Payment.currency) == "RUB")
            .group_by(User.source)
        )).all()
    }

    stats = []
    for link in links:
        buyers, kopecks = paid.get(source_of(link.code), (0, 0))
        stats.append(LinkStats(
            link=link,
            visits=int(visits.get(link.code, 0)),
            new_users=int(new_users.get(link.code, 0)),
            trials=int(trials.get(source_of(link.code), 0)),
            paid_users=buyers,
            revenue_rub=kopecks // 100,
        ))
    return stats, total


def _rub(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


USAGE = (
    "/utm &lt;название&gt; — выпустить новую ссылку\n"
    "/utm — все ссылки и что они принесли"
)


def render_created(link: MirrorUtmLink, bot_username: str) -> str:
    return (
        "✅ <b>Ссылка создана</b>\n\n"
        f"<b>{html.escape(link.title)}</b>\n"
        f"<code>{start_link(bot_username, link.code)}</code>\n\n"
        + bq("Статистика по ссылкам: /utm")
    )


def render_list(stats: list[LinkStats], total: int, bot_username: str) -> str:
    if not stats:
        return "🔗 <b>Рекламные ссылки зеркала</b>\n\n" + bq("Пока ни одной.") + "\n\n" + USAGE
    cards = [
        f"<b>{html.escape(item.link.title)}</b>\n"
        f"<code>{start_link(bot_username, item.link.code)}</code>\n"
        + bq(
            f"Переходов: {item.visits}, из них новых: {item.new_users}",
            f"Пробный период: {item.trials}",
            f"Оплатили: {item.paid_users} на {_rub(item.revenue_rub)}",
        )
        for item in stats
    ]
    shown = f"Показаны последние {len(stats)} из {total}." if total > len(stats) else f"Всего ссылок: {total}."
    return (
        "🔗 <b>Рекламные ссылки зеркала</b>\n\n"
        + "\n\n".join(cards)
        + "\n\n"
        + bq(shown, "Ссылке засчитываются только новые люди: их пробный период и оплаты.")
        + "\n\n"
        + USAGE
    )
