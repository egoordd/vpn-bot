"""Пароли аккаунтов сайта по HTTP: «Забыли пароль?», смена пароля, свой пароль после оплаты.

Подключается в services/http_api.py (``create_app``) и живёт за тем же токеном
API. Ограничители частоты и адрес клиента берутся оттуда же — при запросе, не
при импорте, потому что http_api сам подключает этот модуль.
"""

from __future__ import annotations

from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services import billing_api, mailer, web_checkout, web_delivery, web_passwords

router = APIRouter()

# На одну почту — не больше трёх писем в час: ссылка восстановления не должна
# превращаться в способ засыпать чужой ящик письмами.
_RESET_MAILS_PER_EMAIL = 3
_RESET_MAILS_WINDOW = 3600
_ORDER_PASSWORD_ATTEMPTS = 10
_ORDER_PASSWORD_WINDOW = 600


async def _session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_pool() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_session)]


class ForgotRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Из подписанной сессии сайта, не из того, что набрал браузер.
    telegram_id: int = Field(alias="telegramId")
    current_password: str = Field(alias="currentPassword", min_length=1, max_length=200)
    new_password: str = Field(alias="newPassword", min_length=1, max_length=200)


class OrderPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


async def _allowed(request: Request, account: str) -> bool:
    from services import http_api as core

    return await core._auth_allowed(getattr(request.app.state, "redis", None), request, account)


async def _under(request: Request, bucket: str, key: str, limit: int, window: int) -> bool:
    from services import http_api as core

    return await core._rate_limit_ok(getattr(request.app.state, "redis", None), bucket, key, limit, window)


def _auth_error(exc: billing_api.WebAuthError) -> HTTPException:
    status = {"invalid_credentials": 403, "password_change_not_allowed": 409}.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.code)


@router.post("/web/auth/forgot")
async def web_auth_forgot(body: ForgotRequest, request: Request, session: SessionDep) -> dict[str, Any]:
    """Прислать ссылку для нового пароля. Ответ один и тот же, есть аккаунт или нет."""
    from services import http_api as core

    email = body.email.strip().lower()
    if not core._WEB_EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid_email")
    if not mailer.is_configured():
        raise HTTPException(status_code=503, detail="mail_unavailable")
    if not await _allowed(request, email) or not await _under(
        request, "forgot:email", email, _RESET_MAILS_PER_EMAIL, _RESET_MAILS_WINDOW
    ):
        raise HTTPException(status_code=429, detail="rate_limited")

    issued = await web_passwords.issue_reset(session, email)
    if issued is not None:
        user, token = issued
        await web_delivery.send_reset_letter(user.email or email, token)
    return {"ok": True}


@router.post("/web/auth/reset")
async def web_auth_reset(body: ResetRequest, request: Request, session: SessionDep) -> dict[str, Any]:
    if not await _allowed(request, "reset"):
        raise HTTPException(status_code=429, detail="rate_limited")
    try:
        telegram_id = await web_passwords.reset_password(session, body.token, body.password)
    except billing_api.WebAuthError as exc:
        raise _auth_error(exc) from exc
    return {"ok": True, "telegramId": telegram_id}


@router.post("/web/auth/password")
async def web_auth_change_password(
    body: ChangePasswordRequest, request: Request, session: SessionDep
) -> dict[str, Any]:
    if not await _allowed(request, f"tg:{body.telegram_id}"):
        raise HTTPException(status_code=429, detail="rate_limited")
    try:
        await web_passwords.change_password(
            session,
            telegram_id=body.telegram_id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except billing_api.WebAuthError as exc:
        raise _auth_error(exc) from exc
    return {"ok": True}


@router.post("/web/order/{order_id}/password")
async def web_order_password(
    order_id: str, body: OrderPasswordRequest, request: Request, session: SessionDep
) -> dict[str, Any]:
    """Свой пароль вместо временного — прямо на странице оплаты."""
    if not await _under(
        request, "order:password", order_id, _ORDER_PASSWORD_ATTEMPTS, _ORDER_PASSWORD_WINDOW
    ):
        raise HTTPException(status_code=429, detail="rate_limited")
    try:
        telegram_id = await web_checkout.set_password_from_order(session, order_id, body.password)
    except billing_api.WebAuthError as exc:
        raise _auth_error(exc) from exc
    return {"ok": True, "telegramId": telegram_id}
