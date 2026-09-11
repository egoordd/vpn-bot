"""Lightweight Telegram mirror for account access, paid through Platega.

This process intentionally does not import aiogram.  On the small production
host importing aiogram costs roughly 430 MiB per process, while the raw Bot API
client below stays around 65 MiB together with SQLAlchemy and the panel client.

The mirror shares the primary PostgreSQL database and panel accounts, but it
does not run the main bot's payment handlers, receipt jobs or reminders. Its only
payment rail is Platega (services/mirror_platega.py), switched on by the
PLATEGA_* variables in the mirror's own environment.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.texts import format_gb, format_msk, trial_days
from config import settings
from database.models import Payment, Subscription, User
from database.repository import Repository
from services import billing_api, mirror_legal, mirror_platega, promo
from services.alerts import send_alert
from services.panel_gateway import PanelGatewayError, get_panel_gateway
from services.referral import (
    ReferralError,
    attach_referrer,
    parse_referral_start_payload,
    parse_source_start_payload,
)
from services.subscription import (
    activate_panel_subscription,
    connect_page_url,
    to_gateway_subscription_url,
    to_happ_import_url,
)
from services.tariffs import resolve_tariff


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mirror_bot")

PAYMENT_CALLBACK_PREFIXES = (
    "buy:",
    "buy_tier:",
    "renew_sub:",
    "payyk:",
    "ykemail:",
)
PAYMENT_CALLBACKS = frozenset({"buy_menu", "renew_menu"})
PROMO_STATE_TTL_SECONDS = 15 * 60
PLATEGA_WATCH_SECONDS = 20
PLATEGA_CALLBACK_PREFIXES = ("pl_plan:", "pl_pay:", "pl_check:")


def configured_payment_fields() -> list[str]:
    """Main-bot payment settings that must stay empty in the mirror environment.

    Platega is the mirror's own rail and lives apart (mirror_platega); the main
    bot's YooKassa and Tribute must never be reachable through this token.
    """

    values = {
        "YOOKASSA_SHOP_ID": settings.YOOKASSA_SHOP_ID,
        "YOOKASSA_SECRET_KEY": settings.yookassa_secret_key,
        "TRIBUTE_API_KEY": settings.TRIBUTE_API_KEY,
        "TRIBUTE_DEFAULT_PLAN": settings.TRIBUTE_DEFAULT_PLAN,
    }
    configured = [name for name, value in values.items() if str(value).strip()]
    if settings.TRIBUTE_PLAN_MAP.strip() not in {"", "{}"}:
        configured.append("TRIBUTE_PLAN_MAP")
    if settings.TRIBUTE_PAY_LINKS.strip() not in {"", "{}"}:
        configured.append("TRIBUTE_PAY_LINKS")
    return configured


def assert_payments_disabled() -> None:
    configured = configured_payment_fields()
    if configured:
        raise RuntimeError(
            "Mirror payment integrations must be empty: " + ", ".join(configured)
        )


def is_payment_callback(data: str) -> bool:
    return data in PAYMENT_CALLBACKS or data.startswith(PAYMENT_CALLBACK_PREFIXES)


def _button(text: str, *, callback: str | None = None, url: str | None = None) -> dict[str, str]:
    result = {"text": text}
    if callback is not None:
        result["callback_data"] = callback
    elif url is not None:
        result["url"] = url
    else:  # pragma: no cover - internal programming error
        raise ValueError("button needs callback or url")
    return result


def _keyboard(*rows: list[dict[str, str]]) -> dict[str, list[list[dict[str, str]]]]:
    return {"inline_keyboard": list(rows)}


def main_menu_keyboard(*, has_subscription: bool, trial_available: bool) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    if trial_available:
        rows.append(
            [_button(f"🎁 Активировать пробный период — {trial_days()}", callback="activate_trial")]
        )
    if has_subscription:
        rows.append([_button("📋 Мои подписки", callback="my_subs")])
    rows.append([_button("💳 Тарифы", callback="tariffs")])
    rows.append([_button("🎟 Промокод", callback="promo_enter")])
    rows.append([_button("❓ Помощь", callback="help")])
    rows.append([_button("📄 Пользовательское соглашение", callback="terms")])
    rows.append([_button("🔒 Политика конфиденциальности", callback="privacy")])
    support = _support_button()
    if support is not None:
        rows.append([support])
    return _keyboard(*rows)


def _back_keyboard() -> dict[str, Any]:
    return _keyboard([_button("◀️ В меню", callback="main_menu")])


def _support_button() -> dict[str, str] | None:
    """Direct link to the support account, or None when none is configured."""

    username = settings.support_contact.lstrip("@")
    if not username or username == "не указан":
        return None
    return _button("💬 Поддержка", url=f"https://t.me/{username}")


def _support_keyboard() -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    support = _support_button()
    if support is not None:
        rows.append([support])
    rows.append([_button("◀️ В меню", callback="main_menu")])
    return _keyboard(*rows)


DOCUMENT_CALLBACKS = ("tariffs", "terms", "privacy")


def tariffs_keyboard() -> dict[str, Any]:
    """Tariffs screen: a buy button per paid plan once Platega is switched on."""

    rows: list[list[dict[str, str]]] = []
    if mirror_platega.is_configured():
        for plan in mirror_platega.PAID_PLANS:
            tariff = resolve_tariff(plan)
            rows.append(
                [_button(f"🛒 {tariff.title} — {tariff.price_rub} ₽", callback=f"pl_plan:{plan}")]
            )
    support = _support_button()
    if support is not None:
        rows.append([support])
    rows.append([_button("◀️ В меню", callback="main_menu")])
    return _keyboard(*rows)


def _document_keyboard(name: str) -> dict[str, Any]:
    return tariffs_keyboard() if name == "tariffs" else _support_keyboard()


def _document_text(name: str) -> str:
    """Long-form screen the acquirer's reviewer must be able to reach."""

    if name == "tariffs":
        return mirror_legal.tariffs_text()
    if name == "terms":
        return mirror_legal.terms_of_use()
    if name == "privacy":
        return mirror_legal.privacy_policy()
    raise ValueError(f"unknown document: {name}")


def _tariff_title(plan: str) -> str:
    try:
        return resolve_tariff(plan).title
    except ValueError:
        return plan


def _profile_text(user: User, display_name: str | None) -> str:
    name = html.escape(display_name or user.username or "—")
    return (
        "👤 <b>Профиль</b>\n"
        "<blockquote>"
        f"📝 Имя: {name}\n"
        f"🆔 ID: <code>{user.telegram_id}</code>"
        "</blockquote>"
    )


def _menu_text(
    user: User,
    subscriptions: list[Subscription],
    display_name: str | None,
    *,
    trial_available: bool,
) -> str:
    sections = [_profile_text(user, display_name)]
    if subscriptions:
        nearest = min(subscriptions, key=lambda item: item.expires_at)
        sections.append(
            f"✅ Активных подписок: <b>{len(subscriptions)}</b>\n"
            f"📅 Ближайшее окончание: {format_msk(nearest.expires_at)}\n\n"
            "Подключение и детали — в «📋 Мои подписки»."
        )
    elif trial_available:
        sections.append(
            f"🎁 Доступен <b>бесплатный пробный период — {trial_days()}</b>.\n"
            "Ссылка придёт сразу после активации."
        )
    else:
        sections.append(
            "🔑 Активной подписки нет.\n"
            "Тарифы и цены — в разделе «💳 Тарифы».\n"
            "Оплата в этом боте временно недоступна, оформить подписку поможет поддержка."
        )
    return "\n\n".join(sections)


def _subscription_card(subscription: Subscription) -> str:
    devices = subscription.device_limit if subscription.device_limit is not None else "∞"
    return (
        "📦 <b>Подписка</b>\n"
        "<blockquote>"
        f"💎 Тариф: {html.escape(_tariff_title(subscription.plan))}\n"
        f"📊 Трафик: {format_gb(subscription.traffic_used_bytes or 0)} / "
        f"{format_gb(subscription.traffic_limit_bytes)} ГБ\n"
        f"📱 Устройств: до {devices}\n"
        f"📅 До: {format_msk(subscription.expires_at)}"
        "</blockquote>"
    )


def _subscriptions_text(subscriptions: list[Subscription]) -> str:
    if not subscriptions:
        return (
            "📋 <b>Мои подписки</b>\n\nАктивных подписок нет.\n"
            "Тарифы и цены — в разделе «💳 Тарифы».\n"
            "Оплата в этом боте временно недоступна, оформить подписку поможет поддержка."
        )
    return "📋 <b>Мои подписки</b>\n\n" + "\n\n".join(
        _subscription_card(subscription) for subscription in subscriptions
    )


def _help_text(telegram_id: int) -> str:
    return (
        "❓ <b>Помощь</b>\n\n"
        "<b>Как подключиться</b>\n"
        "<blockquote>"
        "1️⃣ Откройте «Мои подписки»\n"
        "2️⃣ Нажмите «Подключить устройство»\n"
        "3️⃣ Импортируйте ссылку и включите VPN"
        "</blockquote>\n\n"
        "<b>Поддержка</b> — напишите и приложите ID\n"
        "<blockquote>"
        f"{html.escape(settings.support_contact)}\n"
        f"Ваш ID: <code>{telegram_id}</code>"
        "</blockquote>\n\n"
        "<b>Документы</b>\n"
        "<blockquote>"
        "💳 Тарифы\n"
        "📄 Пользовательское соглашение\n"
        "🔒 Политика конфиденциальности\n"
        "Открываются кнопками в главном меню."
        "</blockquote>\n\n"
        f"<code>{mirror_legal.VERIFICATION_CODE}</code>"
    )


def _subscription_access_text(url: str, subscription: Subscription) -> str:
    return (
        "📱 <b>Подключение устройства</b>\n\n"
        f"Тариф: {html.escape(_tariff_title(subscription.plan))}\n"
        "Нажмите <b>«Подключить VPN»</b> — приложение и серверы настроятся сами.\n\n"
        "Ссылка-подписка:\n"
        f"<code>{html.escape(url)}</code>"
    )


def _promo_error_text(exc: promo.PromoError) -> str:
    if isinstance(exc, promo.PromoNotFoundError):
        return "Такого промокода нет. Проверьте написание."
    if isinstance(exc, promo.PromoExpiredError):
        return "Срок действия промокода истёк."
    if isinstance(exc, promo.PromoInactiveError):
        return "Промокод отключён."
    if isinstance(exc, promo.PromoExhaustedError):
        return "Промокод уже исчерпан."
    if isinstance(exc, promo.PromoUserLimitError):
        return "Вы уже использовали этот промокод."
    return "Промокод не подошёл."


class TelegramAPIError(RuntimeError):
    def __init__(self, method: str, description: str, error_code: int | None = None):
        self.method = method
        self.description = description
        self.error_code = error_code
        super().__init__(f"Telegram {method}: {description}")


class TelegramAPI:
    def __init__(self, token: str):
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "TelegramAPI":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=45),
            raise_for_status=False,
        )
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._session is not None:
            await self._session.close()

    async def call(self, method: str, payload: Mapping[str, Any] | None = None) -> Any:
        if self._session is None:  # pragma: no cover - lifecycle guard
            raise RuntimeError("TelegramAPI must be used as an async context manager")
        async with self._session.post(
            f"{self._base_url}/{method}",
            json=dict(payload or {}),
        ) as response:
            try:
                body = await response.json(content_type=None)
            except Exception as exc:  # noqa: BLE001
                raise TelegramAPIError(method, f"HTTP {response.status}") from exc
        if not body.get("ok"):
            raise TelegramAPIError(
                method,
                str(body.get("description") or f"HTTP {response.status}"),
                body.get("error_code"),
            )
        return body.get("result")


class MirrorBot:
    def __init__(
        self,
        api: TelegramAPI,
        session_pool: async_sessionmaker[AsyncSession],
    ):
        self.api = api
        self.session_pool = session_pool
        self._promo_waiting: dict[int, float] = {}
        self._user_locks: dict[int, asyncio.Lock] = {}
        self.platega = mirror_platega.PlategaClient() if mirror_platega.is_configured() else None

    def _lock_for(self, telegram_id: int) -> asyncio.Lock:
        return self._user_locks.setdefault(telegram_id, asyncio.Lock())

    async def render(
        self,
        chat_id: int,
        text: str,
        keyboard: Mapping[str, Any],
        *,
        message_id: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
            "reply_markup": dict(keyboard),
        }
        if message_id is not None:
            payload["message_id"] = message_id
            try:
                await self.api.call("editMessageText", payload)
                return
            except TelegramAPIError as exc:
                if "message is not modified" in exc.description.lower():
                    return
                logger.info("Could not edit message %s; sending a new screen", message_id)
                payload.pop("message_id", None)
        await self.api.call("sendMessage", payload)

    async def answer_callback(self, callback_id: str, text: str = "", *, alert: bool = False) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = alert
        await self.api.call("answerCallbackQuery", payload)

    async def menu_state(
        self,
        telegram_id: int,
        username: str | None,
        display_name: str | None,
    ) -> tuple[str, dict[str, Any]]:
        async with self.session_pool() as session:
            repo = Repository(session)
            user = await repo.get_or_create_user(telegram_id, username)
            subscriptions = await repo.list_active_subscriptions(user.id)
            trial_available = not subscriptions and not await repo.has_used_trial(user.id)
        return (
            _menu_text(
                user,
                subscriptions,
                display_name,
                trial_available=trial_available,
            ),
            main_menu_keyboard(
                has_subscription=bool(subscriptions),
                trial_available=trial_available,
            ),
        )

    async def show_menu(
        self,
        telegram_id: int,
        username: str | None,
        display_name: str | None,
        *,
        chat_id: int,
        message_id: int | None = None,
    ) -> None:
        text, keyboard = await self.menu_state(telegram_id, username, display_name)
        await self.render(chat_id, text, keyboard, message_id=message_id)

    async def record_start(self, user: Mapping[str, Any], payload: str | None) -> None:
        """Best-effort referral/source attribution and funnel recording."""

        try:
            async with self.session_pool() as session:
                repo = Repository(session)
                account = await repo.get_or_create_user(
                    int(user["id"]),
                    user.get("username"),
                )
                ref_code = parse_referral_start_payload(payload)
                if ref_code:
                    try:
                        await attach_referrer(session, user_id=account.id, ref_code=ref_code)
                    except ReferralError:
                        pass
                source = parse_source_start_payload(payload)
                if source:
                    await repo.set_user_source_if_unset(account.id, source)
                await repo.record_funnel_event(
                    account.id,
                    "start",
                    meta={"source": source, "mirror": True},
                )
        except Exception:  # noqa: BLE001 - telemetry must not break the bot
            logger.exception("Failed to record mirror start for telegram_id=%s", user.get("id"))

    async def handle_message(self, message: Mapping[str, Any]) -> None:
        user = message.get("from") or {}
        if not user.get("id") or not message.get("chat"):
            return
        telegram_id = int(user["id"])
        chat_id = int(message["chat"]["id"])
        username = user.get("username")
        display_name = " ".join(
            part for part in (user.get("first_name"), user.get("last_name")) if part
        ) or None
        text = str(message.get("text") or "").strip()
        command, _, payload = text.partition(" ")
        command = command.split("@", 1)[0].lower()

        if command == "/start":
            self._promo_waiting.pop(telegram_id, None)
            await self.record_start(user, payload.strip() or None)
            await self.show_menu(
                telegram_id,
                username,
                display_name,
                chat_id=chat_id,
            )
            return
        if command == "/help":
            await self.render(chat_id, _help_text(telegram_id), _support_keyboard())
            return
        if command.lstrip("/") in DOCUMENT_CALLBACKS:
            await self.render(
                chat_id,
                _document_text(command.lstrip("/")),
                _document_keyboard(command.lstrip("/")),
            )
            return
        if command == "/promo":
            self._promo_waiting[telegram_id] = time.monotonic()
            await self.render(
                chat_id,
                "🎟 <b>Промокод</b>\n\nОтправьте промокод одним сообщением.",
                _back_keyboard(),
            )
            return

        waiting_since = self._promo_waiting.get(telegram_id)
        if waiting_since is not None:
            if time.monotonic() - waiting_since > PROMO_STATE_TTL_SECONDS:
                self._promo_waiting.pop(telegram_id, None)
            elif text:
                await self.redeem_promo(telegram_id, username, text, chat_id)
                return

        await self.show_menu(
            telegram_id,
            username,
            display_name,
            chat_id=chat_id,
        )

    async def handle_callback(self, callback: Mapping[str, Any]) -> None:
        callback_id = str(callback.get("id") or "")
        user = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        if not callback_id or not user.get("id") or not chat.get("id"):
            return
        telegram_id = int(user["id"])
        chat_id = int(chat["id"])
        message_id = int(message["message_id"]) if message.get("message_id") else None
        username = user.get("username")
        display_name = " ".join(
            part for part in (user.get("first_name"), user.get("last_name")) if part
        ) or None
        data = str(callback.get("data") or "")

        if is_payment_callback(data):
            await self.answer_callback(
                callback_id,
                "Оплата временно недоступна. Тарифы — в разделе «Тарифы», оформление — через поддержку.",
                alert=True,
            )
            return
        if data == "main_menu":
            self._promo_waiting.pop(telegram_id, None)
            await self.show_menu(
                telegram_id,
                username,
                display_name,
                chat_id=chat_id,
                message_id=message_id,
            )
            await self.answer_callback(callback_id)
            return
        if data == "help":
            await self.render(
                chat_id,
                _help_text(telegram_id),
                _support_keyboard(),
                message_id=message_id,
            )
            await self.answer_callback(callback_id)
            return
        if data in DOCUMENT_CALLBACKS:
            await self.render(
                chat_id,
                _document_text(data),
                _document_keyboard(data),
                message_id=message_id,
            )
            await self.answer_callback(callback_id)
            return
        if data == "promo_enter":
            self._promo_waiting[telegram_id] = time.monotonic()
            await self.render(
                chat_id,
                "🎟 <b>Промокод</b>\n\nОтправьте промокод одним сообщением.",
                _back_keyboard(),
                message_id=message_id,
            )
            await self.answer_callback(callback_id)
            return
        if data == "activate_trial":
            await self.activate_trial(
                telegram_id,
                username,
                chat_id,
                message_id,
                callback_id,
            )
            return
        if data == "my_subs":
            await self.show_subscriptions(
                telegram_id,
                username,
                chat_id,
                message_id,
                callback_id,
            )
            return
        if data in {"connect_device", "get_key"}:
            await self.show_connection(
                telegram_id,
                chat_id,
                message_id,
                callback_id,
            )
            return
        if data.startswith("connect_loc:"):
            try:
                subscription_id = int(data.split(":", 1)[1])
            except ValueError:
                await self.answer_callback(callback_id, "Некорректная подписка.", alert=True)
                return
            await self.show_connection(
                telegram_id,
                chat_id,
                message_id,
                callback_id,
                subscription_id=subscription_id,
            )
            return
        if data.startswith(PLATEGA_CALLBACK_PREFIXES):
            await self.handle_platega(data, telegram_id, username, chat_id, message_id, callback_id)
            return
        await self.answer_callback(callback_id)

    async def handle_platega(
        self,
        data: str,
        telegram_id: int,
        username: str | None,
        chat_id: int,
        message_id: int | None,
        callback_id: str,
    ) -> None:
        if self.platega is None:
            await self.answer_callback(
                callback_id, "Оплата в боте сейчас недоступна. Напишите в поддержку.", alert=True
            )
            return
        kind, _, rest = data.partition(":")

        if kind == "pl_plan":
            if rest not in mirror_platega.PAID_PLANS:
                await self.answer_callback(callback_id, "Неизвестный тариф.", alert=True)
                return
            rows = [
                [_button(mirror_platega.METHOD_LABELS[method], callback=f"pl_pay:{rest}:{method}")]
                for method in mirror_platega.ENABLED_METHODS
            ]
            rows.append([_button("◀️ К тарифам", callback="tariffs")])
            await self.render(
                chat_id, mirror_platega.checkout_text(rest), _keyboard(*rows), message_id=message_id
            )
            await self.answer_callback(callback_id)
            return

        if kind == "pl_pay":
            plan, _, method_raw = rest.partition(":")
            method = int(method_raw) if method_raw.isdigit() else -1
            if plan not in mirror_platega.PAID_PLANS or method not in mirror_platega.ENABLED_METHODS:
                await self.answer_callback(callback_id, "Неизвестный способ оплаты.", alert=True)
                return
            async with self._lock_for(telegram_id):
                async with self.session_pool() as session:
                    user = await Repository(session).get_or_create_user(telegram_id, username)
                    try:
                        payment, pay_url = await mirror_platega.start_payment(
                            session, self.platega, user=user, plan=plan, method=method
                        )
                    except Exception as exc:  # noqa: BLE001 - surface a retry, alert the owner
                        logger.exception("Platega invoice failed for telegram_id=%s", telegram_id)
                        await send_alert(
                            "⚠️ <b>Не удалось создать счёт Platega в зеркале</b>\n"
                            f"Пользователь: <code>{telegram_id}</code>\n"
                            f"Ошибка: <code>{html.escape(str(exc)[:200])}</code>",
                            throttle_key="mirror-platega-create",
                        )
                        await self.answer_callback(
                            callback_id,
                            "Не удалось создать счёт. Попробуйте через минуту или напишите в поддержку.",
                            alert=True,
                        )
                        return
            keyboard = _keyboard(
                [_button("💳 Оплатить", url=pay_url)],
                [_button("🔄 Проверить оплату", callback=f"pl_check:{payment.id}")],
                [_button("◀️ В меню", callback="main_menu")],
            )
            await self.render(
                chat_id, mirror_platega.invoice_text(plan, method), keyboard, message_id=message_id
            )
            await self.answer_callback(callback_id)
            return

        if kind == "pl_check":
            payment_id = int(rest) if rest.isdigit() else -1
            async with self.session_pool() as session:
                payment = await session.get(Payment, payment_id)
                user = await Repository(session).get_user_by_telegram_id(telegram_id)
                owned = payment is not None and user is not None and payment.user_id == user.id
            if not owned:
                await self.answer_callback(callback_id, "Платёж не найден.", alert=True)
                return
            state = await self.settle_and_notify(payment_id)
            if state in {"completed", "already"}:
                await self.answer_callback(callback_id, "Оплата получена ✅")
            elif state == "pending":
                await self.answer_callback(callback_id, mirror_platega.PENDING_ANSWER, alert=True)
            elif state == "canceled":
                await self.answer_callback(callback_id, mirror_platega.CANCELED_ANSWER, alert=True)
            else:
                await self.answer_callback(callback_id, mirror_platega.PROBLEM_ANSWER, alert=True)
            return

        await self.answer_callback(callback_id)

    async def settle_and_notify(self, payment_id: int) -> str:
        """Settle one invoice; on success hand the buyer their link and tell the owner."""

        if self.platega is None:
            return "pending"
        telegram_id: int | None = None
        subscription: Subscription | None = None
        async with self.session_pool() as session:
            try:
                result = await mirror_platega.settle(session, self.platega, payment_id)
            except mirror_platega.PlategaError as exc:
                logger.warning("Platega status check failed for payment %s: %s", payment_id, exc)
                return "pending"
            payment = result.payment
            if payment is not None:
                owner = await session.get(User, payment.user_id)
                telegram_id = owner.telegram_id if owner is not None else None
            if result.state == "completed":
                subscription = result.subscription

        if result.state == "completed" and subscription is not None and telegram_id is not None:
            url = to_gateway_subscription_url(subscription.subscription_url) or ""
            await self.render(
                telegram_id,
                mirror_platega.paid_text(subscription, format_msk(subscription.expires_at)),
                _keyboard([_button("📋 Мои подписки", callback="my_subs")]),
            )
            await self.render_connection(telegram_id, None, subscription, url)
            await send_alert(
                "💰 <b>Оплата в зеркале (Platega)</b>\n"
                f"Сумма: {payment.amount // 100} ₽\n"
                f"Тариф: {html.escape(_tariff_title(subscription.plan))}\n"
                f"Пользователь: <code>{telegram_id}</code>"
            )
        elif result.state in {"mismatch", "chargeback", "failed"}:
            await send_alert(
                "⚠️ <b>Платёж Platega требует внимания</b>\n"
                f"Платёж: <code>{payment_id}</code>, состояние: <code>{result.state}</code>\n"
                f"Пользователь: <code>{telegram_id}</code>",
                throttle_key=f"mirror-platega-{result.state}:{payment_id}",
            )
        return result.state

    async def platega_watch(self) -> None:
        """Ask Platega about every open invoice, so a paid one is granted without a tap."""

        while True:
            try:
                async with self.session_pool() as session:
                    await mirror_platega.expire_stale(session)
                    open_ids = [payment.id for payment in await mirror_platega.open_payments(session)]
                for payment_id in open_ids:
                    await self.settle_and_notify(payment_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the watcher must keep going
                logger.exception("Platega watcher pass failed")
                await send_alert(
                    "⚠️ <b>Сбой проверки оплат Platega в зеркале</b>\n"
                    f"Ошибка: <code>{html.escape(type(exc).__name__)}</code>",
                    throttle_key="mirror-platega-watch",
                )
            await asyncio.sleep(PLATEGA_WATCH_SECONDS)

    async def activate_trial(
        self,
        telegram_id: int,
        username: str | None,
        chat_id: int,
        message_id: int | None,
        callback_id: str,
    ) -> None:
        async with self._lock_for(telegram_id):
            async with self.session_pool() as session:
                repo = Repository(session)
                user = await repo.get_or_create_user(telegram_id, username)
                if await repo.list_active_subscriptions(user.id):
                    await self.answer_callback(
                        callback_id,
                        "У вас уже есть активная подписка.",
                        alert=True,
                    )
                    return
                if await repo.has_used_trial(user.id):
                    await self.answer_callback(
                        callback_id,
                        "Пробный период уже был активирован ранее.",
                        alert=True,
                    )
                    return
                try:
                    subscription = await activate_panel_subscription(
                        session,
                        user.id,
                        "trial",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Trial activation failed for telegram_id=%s", telegram_id)
                    await send_alert(
                        "⚠️ <b>Ошибка пробного периода в зеркале</b>\n"
                        f"Пользователь: <code>{telegram_id}</code>\n"
                        f"Ошибка: <code>{html.escape(type(exc).__name__)}</code>",
                        throttle_key=f"mirror-trial:{telegram_id}",
                    )
                    await self.answer_callback(
                        callback_id,
                        "Не удалось активировать пробный период. Напишите в поддержку.",
                        alert=True,
                    )
                    return

        url = to_gateway_subscription_url(subscription.subscription_url) or ""
        await self.render_connection(chat_id, message_id, subscription, url)
        await self.answer_callback(callback_id, "Пробный период активирован! 🎉")

    async def show_subscriptions(
        self,
        telegram_id: int,
        username: str | None,
        chat_id: int,
        message_id: int | None,
        callback_id: str,
    ) -> None:
        async with self.session_pool() as session:
            repo = Repository(session)
            user = await repo.get_or_create_user(telegram_id, username)
            subscriptions = await repo.list_active_subscriptions(user.id)
        rows: list[list[dict[str, str]]] = []
        if subscriptions:
            rows.append([_button("📱 Подключить устройство", callback="connect_device")])
        rows.append([_button("◀️ В меню", callback="main_menu")])
        await self.render(
            chat_id,
            _subscriptions_text(subscriptions),
            _keyboard(*rows),
            message_id=message_id,
        )
        await self.answer_callback(callback_id)

    async def _subscription_url(self, subscription: Subscription) -> str | None:
        if subscription.subscription_url:
            return to_gateway_subscription_url(subscription.subscription_url)
        if not subscription.panel_username:
            return None
        panel_user = await get_panel_gateway().get_user(subscription.panel_username)
        return to_gateway_subscription_url(panel_user.subscription_url)

    async def show_connection(
        self,
        telegram_id: int,
        chat_id: int,
        message_id: int | None,
        callback_id: str,
        *,
        subscription_id: int | None = None,
    ) -> None:
        try:
            async with self.session_pool() as session:
                repo = Repository(session)
                user = await repo.get_user_by_telegram_id(telegram_id)
                if user is None:
                    await self.answer_callback(
                        callback_id,
                        "Пользователь не найден. Нажмите /start.",
                        alert=True,
                    )
                    return
                subscriptions = await repo.list_active_subscriptions(user.id)
                if subscription_id is not None:
                    subscriptions = [item for item in subscriptions if item.id == subscription_id]
                resolved: list[tuple[Subscription, str]] = []
                for subscription in subscriptions:
                    url = await self._subscription_url(subscription)
                    if url:
                        resolved.append((subscription, url))
        except PanelGatewayError:
            logger.exception("Could not resolve mirror subscription for telegram_id=%s", telegram_id)
            await self.answer_callback(
                callback_id,
                "Не удалось получить ссылку. Напишите в поддержку.",
                alert=True,
            )
            return

        if not resolved:
            await self.answer_callback(
                callback_id,
                "Активная подписка со ссылкой не найдена.",
                alert=True,
            )
            return
        if len(resolved) > 1 and subscription_id is None:
            rows = [
                [
                    _button(
                        f"{_tariff_title(subscription.plan)} · до {format_msk(subscription.expires_at)}",
                        callback=f"connect_loc:{subscription.id}",
                    )
                ]
                for subscription, _url in resolved
            ]
            rows.append([_button("◀️ В меню", callback="main_menu")])
            await self.render(
                chat_id,
                "📱 <b>Подключение устройства</b>\n\nВыберите подписку:",
                _keyboard(*rows),
                message_id=message_id,
            )
        else:
            subscription, url = resolved[0]
            await self.render_connection(chat_id, message_id, subscription, url)
        await self.answer_callback(callback_id)

    async def render_connection(
        self,
        chat_id: int,
        message_id: int | None,
        subscription: Subscription,
        url: str,
    ) -> None:
        rows: list[list[dict[str, str]]] = []
        site_url = connect_page_url(url)
        auto_url = to_happ_import_url(url, auto=True)
        if site_url:
            rows.append([_button("🔗 Подключить VPN", url=site_url)])
        if auto_url:
            rows.append([_button("⚡️ Автовыбор сервера", url=auto_url)])
        rows.append([_button("◀️ В меню", callback="main_menu")])
        await self.render(
            chat_id,
            _subscription_access_text(url, subscription),
            _keyboard(*rows),
            message_id=message_id,
        )

    async def redeem_promo(
        self,
        telegram_id: int,
        username: str | None,
        code: str,
        chat_id: int,
    ) -> None:
        async with self._lock_for(telegram_id):
            async with self.session_pool() as session:
                repo = Repository(session)
                user = await repo.get_or_create_user(telegram_id, username)
                try:
                    result = await billing_api.redeem_promo(
                        session,
                        user_id=user.id,
                        code=code,
                    )
                except promo.PromoError as exc:
                    await self.render(chat_id, _promo_error_text(exc), _back_keyboard())
                    return
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Promo redemption failed for telegram_id=%s", telegram_id)
                    await send_alert(
                        "⚠️ <b>Ошибка промокода в зеркале</b>\n"
                        f"Пользователь: <code>{telegram_id}</code>\n"
                        f"Ошибка: <code>{html.escape(type(exc).__name__)}</code>",
                        throttle_key=f"mirror-promo:{telegram_id}",
                    )
                    await self.render(
                        chat_id,
                        "Не удалось применить промокод. Напишите в поддержку.",
                        _support_keyboard(),
                    )
                    return
        self._promo_waiting.pop(telegram_id, None)
        await self.render(
            chat_id,
            f"🎉 Промокод применён: подписка на {result.granted_days} дней активна.",
            _keyboard(
                [_button("📱 Подключить устройство", callback="connect_device")],
                [_button("◀️ В меню", callback="main_menu")],
            ),
        )

    async def handle_update(self, update: Mapping[str, Any]) -> None:
        if update.get("message"):
            await self.handle_message(update["message"])
        elif update.get("callback_query"):
            await self.handle_callback(update["callback_query"])

    async def poll(self) -> None:
        offset = 0
        backoff = 1.0
        while True:
            try:
                updates = await self.api.call(
                    "getUpdates",
                    {
                        "offset": offset,
                        "timeout": 30,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
                backoff = 1.0
                for update in updates or []:
                    offset = int(update["update_id"]) + 1
                    try:
                        await self.handle_update(update)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Mirror update %s failed", update.get("update_id"))
                        await send_alert(
                            "⚠️ <b>Ошибка обработки в зеркале</b>\n"
                            f"Update: <code>{update.get('update_id')}</code>\n"
                            f"Ошибка: <code>{html.escape(type(exc).__name__)}</code>",
                            throttle_key=f"mirror-update:{type(exc).__name__}",
                        )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - long polling must recover
                logger.exception("Mirror polling error; retrying in %.1fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 30.0)


async def main() -> None:
    assert_payments_disabled()
    expected_id_raw = os.environ.get("MIRROR_EXPECTED_BOT_ID", "").strip()
    if not expected_id_raw.isdigit():
        raise SystemExit("MIRROR_EXPECTED_BOT_ID is required")
    expected_id = int(expected_id_raw)

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=1,
    )
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with TelegramAPI(settings.bot_token) as api:
            me = await api.call("getMe")
            if int(me["id"]) != expected_id:
                raise SystemExit(
                    f"Mirror token belongs to unexpected bot id {me['id']}; expected {expected_id}"
                )
            mirror_legal.check_document_lengths()
            await api.call("deleteWebhook", {"drop_pending_updates": False})
            await api.call(
                "setMyCommands",
                {
                    "commands": [
                        {"command": "start", "description": "Главное меню"},
                        {"command": "help", "description": "Помощь и поддержка"},
                        {"command": "promo", "description": "Ввести промокод"},
                        {"command": "tariffs", "description": "Тарифы и цены"},
                        {"command": "terms", "description": "Пользовательское соглашение"},
                        {"command": "privacy", "description": "Политика конфиденциальности"},
                    ]
                },
            )
            desired_name = mirror_legal.bot_display_name()
            # setMyName is rate limited, so only touch it when it actually differs.
            current_name = (await api.call("getMyName") or {}).get("name")
            if current_name != desired_name:
                await api.call("setMyName", {"name": desired_name})
                logger.info("Mirror name updated: %r -> %r", current_name, desired_name)
            await api.call(
                "setMyShortDescription",
                {
                    "short_description": (
                        "UnLock VPN: подписка, подключение устройств, тарифы и поддержка."
                    )
                },
            )
            await api.call(
                "setMyDescription",
                {
                    "description": (
                        "UnLock VPN — доступ к защищённому каналу передачи данных.\n\n"
                        "В боте: тарифы и цены, пробный период, подключение устройств, "
                        "промокоды и поддержка.\n"
                        "Пользовательское соглашение и политика конфиденциальности "
                        "открываются кнопками в главном меню."
                    )
                },
            )
            bot = MirrorBot(api, session_pool)
            if bot.platega is not None:
                logger.info(
                    "Mirror started: @%s (%s), payments: Platega %s",
                    me.get("username"), me["id"], mirror_platega.ENABLED_METHODS,
                )
                await asyncio.gather(bot.poll(), bot.platega_watch())
            else:
                logger.info("Mirror started: @%s (%s), payments disabled", me.get("username"), me["id"])
                await bot.poll()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
