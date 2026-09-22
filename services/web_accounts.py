"""Какой аккаунт стоит за почтой — для входа, сброса пароля, регистрации и оплаты.

Почта бывает двух видов. У аккаунта сайта (отрицательный telegram_id) это логин:
её задают при покупке или регистрации. У Telegram-аккаунта это просто адрес для
чеков, который человек вписал сам, без подтверждения. До 22.09.2026 поиск по
почте брал старший аккаунт любого вида, и чужой адрес, вписанный для чеков,
перехватывал вход владельца и его оплаты по почте (аудит, SEC-03).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User


def _same_email(email: str):
    return func.lower(User.email) == (email or "").strip().lower()


async def site_account_by_email(session: AsyncSession, email: str) -> User | None:
    """Аккаунт сайта с этой почтой — тот, чей логин она и есть."""
    return await session.scalar(
        select(User).where(_same_email(email), User.telegram_id < 0).order_by(User.id).limit(1)
    )


async def login_account_by_email(session: AsyncSession, email: str) -> User | None:
    """Чей это логин: аккаунт сайта, а если его нет — Telegram-аккаунт, которому
    пароль сайта уже задали через подтверждение ссылкой подписки."""
    site = await site_account_by_email(session, email)
    if site is not None:
        return site
    return await session.scalar(
        select(User)
        .where(_same_email(email), User.telegram_id > 0, User.web_password_hash.is_not(None))
        .order_by(User.id)
        .limit(1)
    )
