"""Пароль аккаунта на сайте: «Забыли пароль?» и смена пароля в кабинете.

Восстановление идёт через почту аккаунта: на неё уходит одноразовая ссылка,
которая живёт час. В базе лежит только хеш ссылки — утечка таблицы не даёт
войти ни в один аккаунт.
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
    user = await Repository(session).get_user_by_email(email)
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
