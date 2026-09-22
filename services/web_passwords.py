"""Пароль аккаунта на сайте: «Забыли пароль?», смена пароля, выход на всех устройствах.

Восстановление идёт через почту аккаунта: на неё уходит одноразовая ссылка,
которая живёт час. В базе лежит только хеш ссылки — утечка таблицы не даёт
войти ни в один аккаунт.

Сессия сайта несёт отметку состояния входа (``session_stamp``), и сайт сверяет
её с базой на каждом запросе. Отметка меняется со сменой пароля и с «выйти на
всех устройствах», поэтому украденная сессия перестаёт работать, как только
владелец восстановил пароль (аудит 22.09.2026, SEC-04).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from database.models import Base, User, utcnow
from database.repository import Repository

RESET_TTL = timedelta(hours=1)


class WebSessionEpoch(Base):
    """Когда аккаунт последний раз выходил на всех устройствах."""

    __tablename__ = "web_session_epochs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WebPasswordReset(Base):
    """Одноразовая ссылка «задать новый пароль» из письма."""

    __tablename__ = "web_password_resets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    # SQLite в тестах возвращает время без пояса; в базе оно всегда UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def issue_reset(session: AsyncSession, email: str) -> tuple[User, str] | None:
    """Ссылка восстановления для аккаунта с этой почтой. None — такого аккаунта нет."""
    from services.web_accounts import login_account_by_email

    user = await login_account_by_email(session, email)
    if user is None:
        return None
    token = secrets.token_urlsafe(32)
    session.add(WebPasswordReset(token_hash=_digest(token), user_id=user.id, expires_at=utcnow() + RESET_TTL))
    await session.commit()
    return user, token


async def reset_password(session: AsyncSession, token: str, password: str) -> int:
    """Новый пароль по ссылке из письма. Возвращает telegram_id аккаунта."""
    from services import webauth
    from services.billing_api import WebAuthError

    if not webauth.is_password_acceptable(password or ""):
        raise WebAuthError("weak_password")
    row = await session.scalar(
        select(WebPasswordReset).where(WebPasswordReset.token_hash == _digest(token or ""))
    )
    if row is None or row.used_at is not None or _aware(row.expires_at) < utcnow():
        raise WebAuthError("invalid_token")
    user = await Repository(session).get_user(row.user_id)
    if user is None:
        raise WebAuthError("invalid_token")

    now = utcnow()
    user.web_password_hash = webauth.hash_password(password)
    # Остальные ссылки этого аккаунта гаснут: пароль уже задан.
    await session.execute(
        update(WebPasswordReset)
        .where(WebPasswordReset.user_id == user.id, WebPasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    await session.commit()
    return user.telegram_id


async def change_password(
    session: AsyncSession, *, telegram_id: int, current_password: str, new_password: str
) -> None:
    """Смена пароля в кабинете: нужен текущий пароль."""
    from services import webauth
    from services.billing_api import WebAuthError

    user = await Repository(session).get_user_by_telegram_id(telegram_id)
    if user is None or not webauth.verify_password(current_password or "", user.web_password_hash):
        raise WebAuthError("invalid_credentials")
    if not webauth.is_password_acceptable(new_password or ""):
        raise WebAuthError("weak_password")
    user.web_password_hash = webauth.hash_password(new_password)
    await session.commit()


def _stamp(user: User, revoked_at: datetime | None) -> str:
    revoked = int(_aware(revoked_at).timestamp() * 1_000_000) if revoked_at is not None else 0
    material = f"unlock-web-session:{user.id}:{user.telegram_id}:{user.web_password_hash or ''}:{revoked}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


async def session_stamp(session: AsyncSession, telegram_id: int) -> str | None:
    """Отметка входа для сессии сайта. None — аккаунта больше нет."""
    user = await Repository(session).get_user_by_telegram_id(telegram_id)
    if user is None:
        return None
    epoch = await session.get(WebSessionEpoch, user.id)
    return _stamp(user, epoch.revoked_at if epoch is not None else None)


async def sign_out_everywhere(session: AsyncSession, telegram_id: int) -> bool:
    """Все выданные сессии этого аккаунта перестают действовать."""
    user = await Repository(session).get_user_by_telegram_id(telegram_id)
    if user is None:
        return False
    epoch = await session.get(WebSessionEpoch, user.id)
    if epoch is None:
        session.add(WebSessionEpoch(user_id=user.id, revoked_at=utcnow()))
    else:
        epoch.revoked_at = utcnow()
    await session.commit()
    return True
