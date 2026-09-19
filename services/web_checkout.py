"""Покупка на сайте по почте: аккаунт появляется только после оплаты.

До 19.09.2026 оформление сразу заводило аккаунт на указанную почту. Брошенная
оплата оставляла пустой аккаунт, и человек, вернувшийся купить, упирался в «для
этой почты уже есть аккаунт». Теперь до оплаты существует только заказ: почта,
тариф и номер платежа. Аккаунт появляется, когда ЮKassa подтвердила деньги:
новый — с временным паролем в письме; если на почте уже есть аккаунт, оплата
просто продлевает его подписку.

Ссылку подписки страница оплаты показывает только тому, чей аккаунт создан этим
же заказом. Почта публична: иначе любой, заплатив за чужой адрес, увидел бы чужую
ссылку. Владелец адреса получает её письмом.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from database.models import Base, Payment, User, utcnow
from database.repository import Repository

logger = logging.getLogger(__name__)

PENDING = "pending"
COMPLETED = "completed"
CANCELED = "canceled"

# Сколько после оплаты покупатель может заменить временный пароль прямо на
# странице оплаты, не зная его. Дальше — только через кабинет или «Забыли пароль?».
SET_PASSWORD_WINDOW = timedelta(hours=24)
# Заказ старше этого ЮKassa уже не проведёт: брошенная оплата не должна
# мешать регистрации на эту почту.
LIVE_CHECKOUT_WINDOW = timedelta(hours=1)

# Без похожих символов (0/O, 1/l/I): пароль из письма переписывают руками.
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TEMPORARY_PASSWORD_LENGTH = 10


class WebCheckout(Base):
    """Заказ с сайта по почте — до оплаты за ним нет аккаунта."""

    __tablename__ = "web_checkouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Номер заказа в адресе возврата с оплаты (/pay/success?order=...).
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # копейки
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=PENDING, server_default=PENDING, index=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_account: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # Хеш временного пароля, выданного при создании аккаунта: пока пароль тот же,
    # покупатель может заменить его со страницы оплаты.
    initial_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass(frozen=True)
class Fulfilled:
    """Что сделала оплата заказа."""

    payment: Payment
    user: User
    created_account: bool
    temporary_password: str | None


def temporary_password() -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH))


def _aware(value: datetime | None) -> datetime | None:
    # SQLite в тестах возвращает время без пояса; в базе оно всегда UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def existing_account(session: AsyncSession, email: str) -> User | None:
    """Аккаунт, который уже держит эту почту.

    Пустой след брошенной оплаты старого образца (аккаунт без пароля, покупок и
    подписки) не в счёт: за ним ничего нет.
    """
    from services.billing_api import _is_unpaid_guest

    user = await Repository(session).get_user_by_email(email)
    if user is None or await _is_unpaid_guest(session, user):
        return None
    return user


async def start(
    session: AsyncSession, *, email: str, plan: str, amount_kopecks: int, source: str | None
) -> WebCheckout:
    checkout = WebCheckout(
        token=uuid.uuid4().hex, email=email, plan=plan, amount=amount_kopecks, source=source
    )
    session.add(checkout)
    await session.commit()
    await session.refresh(checkout)
    return checkout


async def attach_payment(session: AsyncSession, checkout: WebCheckout, payment_id: str) -> None:
    checkout.payment_id = payment_id
    await session.commit()


async def cancel(session: AsyncSession, checkout: WebCheckout) -> None:
    checkout.status = CANCELED
    await session.commit()


async def find(session: AsyncSession, order_id: str) -> WebCheckout | None:
    """Заказ по номеру из адреса возврата или по номеру платежа ЮKassa."""
    return await session.scalar(
        select(WebCheckout).where(or_(WebCheckout.token == order_id, WebCheckout.payment_id == order_id))
    )


async def _give_temporary_password(session: AsyncSession, checkout: WebCheckout, user: User) -> str:
    from services import webauth

    password = temporary_password()
    password_hash = webauth.hash_password(password)
    user.web_password_hash = password_hash
    checkout.initial_password_hash = password_hash
    await session.commit()
    return password


async def _account_for(session: AsyncSession, checkout: WebCheckout) -> tuple[User, bool, str | None]:
    """Чей это заказ: аккаунт, создан ли он этим заказом, временный пароль."""
    repo = Repository(session)
    if checkout.user_id is not None:
        # Прошлая попытка выдачи успела выбрать аккаунт и оборвалась.
        user = await repo.get_user(checkout.user_id)
        if user is not None:
            untouched = user.web_password_hash == checkout.initial_password_hash
            if checkout.created_account and untouched:
                # Пароль той попытки никуда не ушёл — выдаём новый.
                return user, True, await _give_temporary_password(session, checkout, user)
            return user, checkout.created_account, None

    user = await existing_account(session, checkout.email)
    if user is not None:
        checkout.user_id = user.id
        await session.commit()
        return user, False, None

    # Пустой аккаунт от брошенной оплаты старого образца ничего не держит —
    # занимаем его, чтобы на одной почте не было двух аккаунтов.
    user = await repo.get_user_by_email(checkout.email)
    if user is None:
        user = await repo.create_user(telegram_id=-(secrets.randbits(52) + 1))
        user = await repo.update_user(user.id, email=checkout.email) or user
    checkout.user_id = user.id
    checkout.created_account = True
    return user, True, await _give_temporary_password(session, checkout, user)


async def fulfill(session: AsyncSession, payment_id: str) -> Fulfilled | None:
    """Оплаченный заказ → аккаунт и проведённый платёж.

    None — такого заказа нет или его уже выдали. Платёж заводится с обычной
    для ЮKassa нагрузкой ``unlock:<user>:<plan>:<token>``, поэтому дальше вебхук,
    чеки и статистика работают с ним как с любым другим.
    """
    checkout = await session.scalar(select(WebCheckout).where(WebCheckout.payment_id == payment_id))
    if checkout is None or checkout.status == COMPLETED:
        return None

    repo = Repository(session)
    user, created, password = await _account_for(session, checkout)
    if await repo.get_payment_by_external_id(payment_id) is None:
        await repo.create_yookassa_payment(
            user_id=user.id,
            amount=checkout.amount,
            external_invoice_id=payment_id,
            invoice_payload=f"unlock:{user.id}:{checkout.plan}:{checkout.token}",
            plan=checkout.plan,
        )
    payment = await repo.complete_payment_by_external_id(payment_id, provider="yookassa")
    if payment is None:
        # Этот платёж уже провела параллельная выдача.
        return None

    checkout.status = COMPLETED
    checkout.completed_at = utcnow()
    await session.commit()
    if checkout.source:
        await repo.set_user_source_if_unset(user.id, checkout.source)
    return Fulfilled(payment=payment, user=user, created_account=created, temporary_password=password)


async def can_set_password(session: AsyncSession, checkout: WebCheckout) -> bool:
    """Можно ли со страницы оплаты заменить временный пароль своим."""
    if checkout.status != COMPLETED or not checkout.created_account or checkout.user_id is None:
        return False
    completed_at = _aware(checkout.completed_at)
    if completed_at is None or completed_at < utcnow() - SET_PASSWORD_WINDOW:
        return False
    user = await Repository(session).get_user(checkout.user_id)
    return user is not None and user.web_password_hash == checkout.initial_password_hash


async def set_password_from_order(session: AsyncSession, order_id: str, password: str) -> int:
    """Покупатель задаёт свой пароль прямо на странице оплаты. Возвращает telegram_id.

    Только для аккаунта, созданного этим заказом, пока на нём временный пароль
    из письма, и в первые сутки: номер заказа знает лишь браузер покупателя.
    """
    from services import webauth
    from services.billing_api import WebAuthError

    if not webauth.is_password_acceptable(password or ""):
        raise WebAuthError("weak_password")
    checkout = await find(session, order_id)
    if checkout is None or not await can_set_password(session, checkout):
        raise WebAuthError("password_change_not_allowed")
    user = await Repository(session).get_user(checkout.user_id)
    if user is None:
        raise WebAuthError("password_change_not_allowed")
    user.web_password_hash = webauth.hash_password(password)
    await session.commit()
    return user.telegram_id


async def may_still_pay(session: AsyncSession, email: str) -> bool:
    """Идёт ли по этой почте оплата, которая ещё может пройти.

    ЮKassa молча отменяет брошенные оплаты, поэтому спрашиваем её саму. Что
    неясно — считаем живым.
    """
    from services import yookassa

    rows = (
        await session.scalars(
            select(WebCheckout).where(WebCheckout.email == email, WebCheckout.status == PENDING)
        )
    ).all()
    fresh_since = utcnow() - LIVE_CHECKOUT_WINDOW
    for checkout in rows:
        if not checkout.payment_id or _aware(checkout.created_at) < fresh_since:
            continue
        try:
            remote = await yookassa.get_payment(checkout.payment_id)
        except Exception:  # noqa: BLE001 - ЮKassa недоступна: оплата могла пройти
            return True
        if str(remote.get("status") or "").strip().lower() == "canceled":
            await cancel(session, checkout)
            continue
        return True
    return False
