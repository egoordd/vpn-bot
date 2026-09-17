"""/utm — рекламные ссылки в бота: выпуск, учёт переходов и что они принесли.

Ссылка вида ``t.me/<бот>?start=utm_<code>``: код из 8 случайных символов,
запись в ``utm_links``. Каждый /start по ней пишется в ``utm_visits``, а новый
человек получает ``users.source = "utm_<code>"`` — по этому источнику ссылке
засчитываются его пробный период и оплаты (и он же виден в /funnel).

Уже знакомым людям источник не ставится: иначе реклама забрала бы себе оплаты
старого клиента, который просто нажал ссылку ещё раз.
"""

from __future__ import annotations

import html
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import bq
from database.models import FunnelEvent, Payment, User, UtmLink, UtmVisit

START_PREFIX = "utm_"
CODE_LENGTH = 8
TITLE_MAX = 64
LIST_LIMIT = 20
_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_CODE_RE = re.compile(rf"[a-z0-9]{{{CODE_LENGTH}}}")


def new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


def source_of(code: str) -> str:
    return f"{START_PREFIX}{code}"


def start_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username.lstrip('@')}?start={source_of(code)}"


def parse_start_payload(payload: str | None) -> str | None:
    """Код из `/start utm_<code>`, если он вообще похож на наш; иначе None."""
    if not payload:
        return None
    payload = payload.strip()
    if not payload.startswith(START_PREFIX):
        return None
    code = payload[len(START_PREFIX):]
    return code if _CODE_RE.fullmatch(code) else None


async def get(session: AsyncSession, code: str) -> UtmLink | None:
    return await session.scalar(select(UtmLink).where(UtmLink.code == code))


async def create(session: AsyncSession, *, title: str, created_by: int | None) -> UtmLink:
    clean = " ".join((title or "").split())[:TITLE_MAX]
    if not clean:
        raise ValueError("title_required")
    for _ in range(5):
        code = new_code()
        if await get(session, code) is None:
            break
    else:  # 36⁸ вариантов: пять совпадений подряд значат, что сломан генератор
        raise RuntimeError("could not pick a free utm code")
    link = UtmLink(code=code, title=clean, created_by=created_by)
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def register_start(session: AsyncSession, *, user: User, code: str, is_new_user: bool) -> bool:
    """Записать переход по ссылке. False — такой ссылки мы не выпускали."""
    if await get(session, code) is None:
        return False
    session.add(UtmVisit(code=code, user_id=user.id, is_new_user=is_new_user))
    if is_new_user and not user.source:
        user.source = source_of(code)
    await session.commit()
    return True


@dataclass(frozen=True)
class LinkStats:
    link: UtmLink
    visits: int = 0
    new_users: int = 0
    trials: int = 0
    paid_users: int = 0
    revenue_rub: int = 0


async def collect(session: AsyncSession, *, limit: int = LIST_LIMIT) -> tuple[list[LinkStats], int]:
    """Свежие ссылки со статистикой и общее число выпущенных ссылок."""
    total = int(await session.scalar(select(func.count(UtmLink.id))) or 0)
    links = (
        await session.scalars(select(UtmLink).order_by(UtmLink.created_at.desc(), UtmLink.id.desc()).limit(limit))
    ).all()
    if not links:
        return [], total
    codes = [link.code for link in links]
    sources = {source_of(code): code for code in codes}

    visits = dict(
        (await session.execute(
            select(UtmVisit.code, func.count(UtmVisit.id)).where(UtmVisit.code.in_(codes)).group_by(UtmVisit.code)
        )).all()
    )
    new_users = dict(
        (await session.execute(
            select(UtmVisit.code, func.count(UtmVisit.user_id.distinct()))
            .where(UtmVisit.code.in_(codes), UtmVisit.is_new_user.is_(True))
            .group_by(UtmVisit.code)
        )).all()
    )
    trials = dict(
        (await session.execute(
            select(User.source, func.count(User.id.distinct()))
            .join(FunnelEvent, FunnelEvent.user_id == User.id)
            .where(User.source.in_(sources), FunnelEvent.event == "trial")
            .group_by(User.source)
        )).all()
    )
    completed = (Payment.status == "completed", func.upper(Payment.currency) == "RUB")
    paid = {
        source: (int(buyers), int(kopecks))
        for source, buyers, kopecks in (await session.execute(
            select(User.source, func.count(User.id.distinct()), func.coalesce(func.sum(Payment.amount), 0))
            .join(Payment, Payment.user_id == User.id)
            .where(User.source.in_(sources), *completed)
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


def render_created(link: UtmLink, bot_username: str) -> str:
    return (
        "✅ <b>Ссылка создана</b>\n\n"
        f"<b>{html.escape(link.title)}</b>\n"
        f"<code>{start_link(bot_username, link.code)}</code>\n\n"
        + bq("Статистика по ссылкам: /utm")
    )


def render_list(stats: list[LinkStats], total: int, bot_username: str) -> str:
    if not stats:
        return "🔗 <b>Рекламные ссылки</b>\n\n" + bq("Пока ни одной.") + "\n\n" + USAGE
    cards = []
    for item in stats:
        cards.append(
            f"<b>{html.escape(item.link.title)}</b>\n"
            f"<code>{start_link(bot_username, item.link.code)}</code>\n"
            + bq(
                f"Переходов: {item.visits}, из них новых: {item.new_users}",
                f"Пробный период: {item.trials}",
                f"Оплатили: {item.paid_users} на {_rub(item.revenue_rub)}",
            )
        )
    shown = f"Показаны последние {len(stats)} из {total}." if total > len(stats) else f"Всего ссылок: {total}."
    return (
        "🔗 <b>Рекламные ссылки</b>\n\n"
        + "\n\n".join(cards)
        + "\n\n"
        + bq(
            shown,
            "Рекламе засчитываются только новые люди: пробный период и оплаты тех, кто впервые пришёл по ссылке.",
        )
        + "\n\n"
        + USAGE
    )
