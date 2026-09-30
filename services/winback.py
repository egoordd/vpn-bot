"""Личное предложение тем, кто взял пробник и так и не подключился.

Человеку, у которого пробник кончился больше суток назад, а трафика так и не
было и оплат нет, бот один раз присылает безлимит со скидкой ~10%: 30 дней за
179 ₽, 3 месяца за 489 ₽, 6 месяцев за 899 ₽ (скрытые тарифы winback_* в
services/tariffs.py). Предложение действует 72 часа; купить по нему можно один
раз. Кто и когда его получил, помнит таблица winback_offers — по ней же бот
решает, открывать ли скидочный тариф (bot/handlers/buy.py).

Рассылкой занимается планировщик раз в день в 22:00 по Москве, пока WINBACK_ENABLED включён.
Решение владельца 01.10.2026.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import DateTime, ForeignKey, Integer, String, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from bot.texts import format_msk
from config import settings
from database.models import Base, FunnelEvent, Payment, Subscription, User
from services.tariffs import TARIFFS

logger = logging.getLogger(__name__)

WINBACK_PLANS = ("winback_unlim_1m", "winback_unlim_3m", "winback_unlim_6m")
# Обычный тариф той же длины — для зачёркнутой цены в сообщении.
_REGULAR_FOR = {
    "winback_unlim_1m": "standard_1m",
    "winback_unlim_3m": "standard_3m",
    "winback_unlim_6m": "standard_6m",
}
OFFER_TTL = timedelta(hours=72)
# Пишем не сразу после пробника, а через сутки: вдруг человек как раз покупает.
QUIET_AFTER_TRIAL = timedelta(hours=24)
BATCH_LIMIT = 200
SEND_PAUSE_SECONDS = 1.0

_PAID_STATUSES = ("completed", "paid", "succeeded")
SENT = "sent"
FAILED = "failed"


class WinbackOffer(Base):
    """Кому и когда отправлено предложение. Одна строка на человека."""

    __tablename__ = "winback_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)


def is_winback_plan(plan: str) -> bool:
    return plan in WINBACK_PLANS


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _paid_any():
    return exists().where(Payment.user_id == User.id, Payment.status.in_(_PAID_STATUSES))


async def find_candidates(session: AsyncSession, *, now: datetime, limit: int = BATCH_LIMIT) -> list[User]:
    """Кто взял пробник, не подключился, не платил и ещё не получал предложение."""

    trial_ended = (
        select(func.max(Subscription.expires_at))
        .where(Subscription.user_id == User.id, Subscription.plan == "trial")
        .scalar_subquery()
    )
    had_traffic = exists().where(Subscription.user_id == User.id, Subscription.traffic_used_bytes > 0)
    connected = exists().where(FunnelEvent.user_id == User.id, FunnelEvent.event == "first_connect")
    paid_access = exists().where(
        Subscription.user_id == User.id,
        Subscription.plan != "trial",
        Subscription.is_active.is_(True),
        Subscription.expires_at > now,
    )
    offered = exists().where(WinbackOffer.user_id == User.id)
    query = (
        select(User)
        .where(
            User.telegram_id > 0,
            User.is_blocked.is_(False),
            trial_ended.is_not(None),
            trial_ended <= now - QUIET_AFTER_TRIAL,
            ~had_traffic,
            ~connected,
            ~_paid_any(),
            ~paid_access,
            ~offered,
        )
        .order_by(User.id)
        .limit(limit)
    )
    return list((await session.execute(query)).scalars())


async def _record(
    session: AsyncSession, user_id: int, *, now: datetime, status: str, error: str | None = None
) -> WinbackOffer:
    offer = (
        await session.execute(select(WinbackOffer).where(WinbackOffer.user_id == user_id))
    ).scalar_one_or_none()
    if offer is None:
        offer = WinbackOffer(user_id=user_id)
        session.add(offer)
    offer.sent_at = now
    offer.expires_at = now + OFFER_TTL
    offer.status = status
    offer.error = error
    await session.commit()
    await session.refresh(offer)
    return offer


async def grant_offer(session: AsyncSession, user_id: int, *, now: datetime | None = None) -> WinbackOffer:
    """Открыть (или продлить) предложение на 72 часа — для рассылки и для проверки админом."""

    return await _record(session, user_id, now=now or datetime.now(timezone.utc), status=SENT)


async def active_offer(session: AsyncSession, user_id: int, *, now: datetime | None = None) -> WinbackOffer | None:
    """Действующее предложение: отправлено, не истекло и скидкой ещё не пользовались."""

    now = now or datetime.now(timezone.utc)
    offer = (
        await session.execute(
            select(WinbackOffer).where(WinbackOffer.user_id == user_id, WinbackOffer.status == SENT)
        )
    ).scalar_one_or_none()
    if offer is None or _aware(offer.expires_at) <= now:
        return None
    used = await session.execute(
        select(
            or_(
                exists().where(Subscription.user_id == user_id, Subscription.plan.in_(WINBACK_PLANS)),
                exists().where(
                    and_(
                        Payment.user_id == user_id,
                        Payment.status.in_(_PAID_STATUSES),
                        or_(*(Payment.invoice_payload.contains(f":{plan}:") for plan in WINBACK_PLANS)),
                    )
                ),
            )
        )
    )
    return None if used.scalar() else offer


async def purchase_allowed(session: AsyncSession, telegram_id: int, plan: str) -> bool:
    """Обычные тарифы открыты всем, скидочные — только держателю предложения."""

    if not is_winback_plan(plan):
        return True
    user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    return user is not None and await active_offer(session, user.id) is not None


async def stats(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Сводка для админа: кто подходит сейчас, кому ушло, сколько купили."""

    now = now or datetime.now(timezone.utc)

    async def count(query) -> int:
        return int((await session.execute(query)).scalar() or 0)

    return {
        "candidates": len(await find_candidates(session, now=now, limit=100_000)),
        "sent": await count(select(func.count()).select_from(WinbackOffer).where(WinbackOffer.status == SENT)),
        "failed": await count(select(func.count()).select_from(WinbackOffer).where(WinbackOffer.status == FAILED)),
        "purchased": await count(
            select(func.count(func.distinct(Subscription.user_id))).where(Subscription.plan.in_(WINBACK_PLANS))
        ),
    }


def offer_view(expires_at: datetime) -> tuple[str, InlineKeyboardMarkup]:
    lines = []
    buttons = []
    for code in WINBACK_PLANS:
        tariff = TARIFFS[code]
        regular = TARIFFS[_REGULAR_FOR[code]].price_rub
        label = tariff.title.removeprefix("Безлимит ")
        lines.append(f"• {label} — <s>{regular} ₽</s> <b>{tariff.price_rub} ₽</b>")
        buttons.append(
            [InlineKeyboardButton(text=f"♾ {label} — {tariff.price_rub} ₽", callback_data=f"buy:{code}")]
        )
    buttons.append([InlineKeyboardButton(text="❓ Не получилось подключиться", callback_data="help")])
    text = (
        "🎁 <b>Персональное предложение</b>\n\n"
        "Вы брали пробный период, но так и не подключились. Давайте попробуем ещё раз — "
        "на особых условиях, <b>без ограничения трафика</b>:\n\n"
        + "\n".join(lines)
        + "\n\n📱 До 3 устройств · ⚡️ Авто-обход · 🇷🇺 российские сервисы работают\n"
        f"⏳ Предложение действует до {format_msk(expires_at)}\n\n"
        "Если в прошлый раз что-то не получилось, нажмите «Не получилось подключиться» — поможем."
    )
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_winback_offers(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
    *,
    now: datetime | None = None,
    pause: float = SEND_PAUSE_SECONDS,
) -> int:
    """Разослать предложение всем, кто подходит. Возвращает, скольким доставлено."""

    if not settings.WINBACK_ENABLED:
        return 0
    now = now or datetime.now(timezone.utc)
    async with session_pool() as session:
        candidates = [(user.id, user.telegram_id) for user in await find_candidates(session, now=now)]

    delivered = 0
    for user_id, telegram_id in candidates:
        text, keyboard = offer_view(now + OFFER_TTL)
        try:
            await bot.send_message(telegram_id, text, reply_markup=keyboard)
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            # Бот заблокирован или чат не существует: второй раз не пробуем.
            async with session_pool() as session:
                await _record(session, user_id, now=now, status=FAILED, error=str(exc)[:255])
            continue
        except Exception:  # noqa: BLE001 — сеть: без записи, повторим в следующий час
            logger.exception("winback: не удалось отправить user_id=%s", user_id)
            continue
        async with session_pool() as session:
            await _record(session, user_id, now=now, status=SENT)
        delivered += 1
        if pause:
            await asyncio.sleep(pause)
    if candidates:
        logger.info("winback: кандидатов %s, доставлено %s", len(candidates), delivered)
    return delivered
