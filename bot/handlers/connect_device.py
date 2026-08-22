import html
import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq, format_msk
from services.tariffs import resolve_tariff
from database.models import Subscription
from database.repository import Repository
from services.panel_gateway import PanelGatewayError, get_panel_gateway
from services import mailer
from services.qrcode import generate_qr_png_bytes
from services.subscription import connect_page_url, to_gateway_subscription_url, to_happ_import_url
from services.wireguard import WireGuardError, rotate_user_key

logger = logging.getLogger(__name__)
router = Router()


def _location_label(subscription: Subscription) -> str:
    if subscription.tier == "premium":
        return "💎 Premium"
    return "🌐 Обычный"


def _sub_choice_label(subscription: Subscription) -> str:
    """Distinguishing label for the multi-subscription picker: tariff + expiry,
    so two active subscriptions are never indistinguishable."""
    try:
        title = resolve_tariff(subscription.plan).title
    except ValueError:
        title = subscription.plan
    return f"{_location_label(subscription)} · {title} · до {format_msk(subscription.expires_at)}"


def _connect_device_keyboard(
    sub_id: int | None = None,
    site_url: str | None = None,
    auto_url: str | None = None,
) -> InlineKeyboardMarkup:
    suffix = f":{sub_id}" if sub_id is not None else ""
    rows: list[list[InlineKeyboardButton]] = []
    if site_url:
        rows.append([InlineKeyboardButton(text="🔗 Подключить VPN", url=site_url)])
    if auto_url:
        rows.append([InlineKeyboardButton(text="⚡️ Авто-обход — все локации", url=auto_url)])
    # A customer in Russia cannot open Telegram without a working tunnel, so the
    # screen that hands out the link is unreachable exactly when it is needed —
    # "чтобы подключить VPN, надо включить другой". Mail puts the link somewhere
    # that survives losing the tunnel.
    rows.append([InlineKeyboardButton(text="📧 Прислать ссылку на почту", callback_data=f"connect_mail{suffix}")])
    rows.append([InlineKeyboardButton(text="❓ Как подключить вручную", callback_data=f"connect_help{suffix}")])
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _location_selector_keyboard(subs: list[Subscription]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_sub_choice_label(sub), callback_data=f"connect_loc:{sub.id}")]
        for sub in subs
    ]
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _manual_help_keyboard(sub_id: int | None = None) -> InlineKeyboardMarkup:
    back = f"connect_loc:{sub_id}" if sub_id is not None else "connect_device"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К подключению", callback_data=back)],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
        ]
    )


def _subscription_access_text(subscription_url: str, location: str | None = None) -> str:
    """Screen text for a ready subscription.

    Deliberately short: the buttons below already name what they do, so
    narrating each one just buries the two things the text alone can carry —
    which button to press first, and the link itself. Emphasis is spent on the
    single primary action; an emoji on every line (as before) flattens the
    hierarchy until nothing stands out.
    """
    escaped_url = html.escape(subscription_url)
    header = "📱 <b>Подключение устройства</b>"
    if location:
        header += f"\n{location}"
    return (
        f"{header}\n\n"
        "Нажмите <b>«Подключить VPN»</b> — приложение и серверы\n"
        "настроятся сами.\n\n"
        "Ссылка-подписка:\n"
        f"<code>{escaped_url}</code>\n\n"
        + bq("♻️ Сменили тариф или локацию — «Обновить подписку» в приложении.")
    )


async def _resolve_url_for_subscription(repo: Repository, subscription: Subscription) -> str | None:
    if not subscription.panel_username:
        return None
    if subscription.subscription_url:
        return to_gateway_subscription_url(subscription.subscription_url)
    panel_user = await get_panel_gateway().get_user(subscription.panel_username)
    return to_gateway_subscription_url(panel_user.subscription_url)


async def _active_subs_with_links(repo: Repository, user_id: int) -> list[tuple[Subscription, str]]:
    result: list[tuple[Subscription, str]] = []
    for sub in await repo.list_active_subscriptions(user_id):
        url = await _resolve_url_for_subscription(repo, sub)
        if url:
            result.append((sub, url))
    return result


async def _send_subscription_screen(callback: CallbackQuery, subscription: Subscription, url: str) -> None:
    # Text-only screen: the link + buttons cover every path (site page with
    # apps and «Авто-обход», direct Happ import) — no QR image is pushed.
    await show_screen(
        callback,
        _subscription_access_text(url, _location_label(subscription)),
        _connect_device_keyboard(
            subscription.id,
            site_url=connect_page_url(url),
            auto_url=to_happ_import_url(url, auto=True),
        ),
    )


def _manual_help_text(subscription_url: str | None) -> str:
    lines = [
        "📖 <b>Как подключить вручную</b>",
        "",
        bq(
            "1️⃣ Скопируйте ссылку-подписку (ниже) — нажмите на неё.",
            "2️⃣ Откройте приложение и импортируйте ссылку («Добавить из буфера»).",
            "3️⃣ Включите туннель и выберите страну.",
        ),
        "",
        "<b>Приложения, которые поддерживают ссылку:</b>",
        bq(
            "🍏 iOS — Happ, V2RayTun, Streisand",
            "🤖 Android — Happ, V2RayTun, Hiddify, sing-box",
        ),
    ]
    if subscription_url:
        lines.extend(["", "🔗 <b>Ссылка-подписка:</b>", f"<code>{html.escape(subscription_url)}</code>"])
    lines.extend(["", "♻️ Сменили тариф или локацию? Нажмите «Обновить подписку» в приложении."])
    return "\n".join(lines)


async def _send_processing_error(callback: CallbackQuery, text: str) -> None:
    if callback.message:
        await callback.message.answer(text, reply_markup=back_to_menu_keyboard())


async def _resolve_subscription_url(repo: Repository, user_id: int) -> str | None:
    subscription = await repo.get_active_subscription(user_id)
    if subscription is None or not subscription.panel_username:
        return None
    if subscription.subscription_url:
        return to_gateway_subscription_url(subscription.subscription_url)

    panel_user = await get_panel_gateway().get_user(subscription.panel_username)
    return to_gateway_subscription_url(panel_user.subscription_url)


async def _get_user_and_subscription_url(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> tuple[int | None, str | None]:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        if user is None:
            await callback.answer("Пользователь не найден. Нажмите /start.", show_alert=True)
            return None, None

        try:
            subscription_url = await _resolve_subscription_url(repo, user.id)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URL for user_id=%s", user.id)
            await callback.answer("Не удалось получить ссылку-подписку. Напишите в поддержку.", show_alert=True)
            return None, None

        return user.id, subscription_url


@router.callback_query(F.data.in_({"connect_device", "get_key"}), flags={"subscription_required": True})
async def connect_device_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        if user is None:
            await callback.answer("Пользователь не найден. Нажмите /start.", show_alert=True)
            return
        user_id = user.id
        await callback.answer()
        try:
            subs_with_links = await _active_subs_with_links(repo, user_id)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URLs for user_id=%s", user_id)
            await _send_processing_error(callback, "Не удалось получить ссылку-подписку. Напишите в поддержку.")
            return

    if len(subs_with_links) > 1:
        subs = [sub for sub, _ in subs_with_links]
        text = (
            "📱 <b>Подключение устройства</b>\n\n"
            "У вас несколько подписок. Выберите, какую подключить:"
        )
        await show_screen(callback, text, _location_selector_keyboard(subs))
        return

    if len(subs_with_links) == 1:
        subscription, url = subs_with_links[0]
        await _send_subscription_screen(callback, subscription, url)
        return

    async with session_pool() as session:
        try:
            _, config_text = await rotate_user_key(session=session, user_id=user_id)
        except WireGuardError:
            logger.exception("Could not provide WireGuard key for user_id=%s", user_id)
            await _send_processing_error(callback, "Не удалось подготовить ключ. Напишите в поддержку.")
            return

    qr_bytes = await generate_qr_png_bytes(config_text)
    filename = f"wireguard_{callback.from_user.id}.conf"
    if callback.message:
        await callback.message.answer_document(
            BufferedInputFile(config_text.encode("utf-8"), filename=filename),
            caption="Ваш WireGuard-конфиг.",
        )
        await callback.message.answer_photo(
            BufferedInputFile(qr_bytes, filename="wireguard_qr.png"),
            caption="QR-код для импорта в WireGuard.",
            reply_markup=back_to_menu_keyboard(),
        )


@router.callback_query(F.data.startswith("connect_loc:"), flags={"subscription_required": True})
async def connect_location_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    try:
        sub_id = int(callback.data.split(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Подписка не найдена", show_alert=True)
        return
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        subscription = await repo.get_subscription(sub_id) if user else None
        if user is None or subscription is None or subscription.user_id != user.id:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        await callback.answer()
        try:
            url = await _resolve_url_for_subscription(repo, subscription)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URL for sub_id=%s", sub_id)
            await _send_processing_error(callback, "Не удалось получить ссылку. Напишите в поддержку.")
            return
    if not url:
        await _send_processing_error(callback, "Для этой подписки нет ссылки.")
        return
    await _send_subscription_screen(callback, subscription, url)


@router.callback_query(F.data.startswith("connect_help"), flags={"subscription_required": True})
async def connect_help_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    parts = callback.data.split(":") if callback.data else []
    sub_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        if user is None:
            await callback.answer("Пользователь не найден. Нажмите /start.", show_alert=True)
            return
        await callback.answer()
        subscription_url: str | None = None
        try:
            if sub_id is not None:
                subscription = await repo.get_subscription(sub_id)
                if subscription and subscription.user_id == user.id:
                    subscription_url = await _resolve_url_for_subscription(repo, subscription)
            if subscription_url is None:
                subscription_url = await _resolve_subscription_url(repo, user.id)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URL for help, user_id=%s", user.id)
            subscription_url = None

    if callback.message:
        await callback.message.answer(
            _manual_help_text(subscription_url),
            reply_markup=_manual_help_keyboard(sub_id),
        )




_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ConnectEmailInput(StatesGroup):
    email = State()


def _email_prompt_keyboard(sub_id: int | None) -> InlineKeyboardMarkup:
    back = f"connect_loc:{sub_id}" if sub_id is not None else "connect_device"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=back)],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
        ]
    )


def _subscription_email_body(url: str) -> tuple[str, str]:
    text = (
        "Ваша ссылка-подписка UnLock VPN:\n\n"
        f"{url}\n\n"
        "Как подключиться:\n"
        "1. Установите приложение — https://unlockvpn.site/download\n"
        "2. Добавьте в него эту ссылку.\n"
        "3. Включите туннель.\n\n"
        "Ссылка постоянная: сохраните это письмо, и доступ можно будет восстановить "
        "даже без Telegram.\n\n"
        "Помощь: https://t.me/unlock_support_bot"
    )
    safe = html.escape(url)
    body = (
        "<p>Ваша ссылка-подписка <b>UnLock VPN</b>:</p>"
        f'<p><a href="{safe}">{safe}</a></p>'
        "<p>Как подключиться:</p><ol>"
        '<li>Установите приложение — <a href="https://unlockvpn.site/download">'
        "unlockvpn.site/download</a></li>"
        "<li>Добавьте в него эту ссылку.</li><li>Включите туннель.</li></ol>"
        "<p>Ссылка постоянная: сохраните это письмо, и доступ можно будет восстановить "
        "даже без Telegram.</p>"
    )
    return text, body


@router.callback_query(F.data.startswith("connect_mail"))
async def connect_email_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = (callback.data or "").partition(":")
    sub_id = int(raw_id) if raw_id.isdigit() else None
    if not mailer.is_configured():
        await callback.answer("Отправка почты сейчас недоступна", show_alert=True)
        return
    await state.set_state(ConnectEmailInput.email)
    await state.update_data(sub_id=sub_id)
    await show_screen(
        callback,
        "📧 <b>Ссылка на почту</b>\n\n"
        "Отправьте адрес — пришлём вашу ссылку-подписку письмом.\n\n"
        + bq(
            "Письмо пригодится, когда Telegram недоступен:",
            "ссылку можно будет взять из почты и подключиться без бота.",
        ),
        _email_prompt_keyboard(sub_id),
    )
    await callback.answer()


@router.message(ConnectEmailInput.email)
async def connect_email_message_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    email = (message.text or "").strip()
    data = await state.get_data()
    sub_id = data.get("sub_id")
    if not _EMAIL_RE.match(email) or len(email) > 320:
        await message.answer(
            "Это не похоже на email. Отправьте адрес вида <code>name@mail.ru</code>.",
            reply_markup=_email_prompt_keyboard(sub_id),
        )
        return

    await state.clear()
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        try:
            subs_with_links = await _active_subs_with_links(repo, user.id)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URL for email delivery user_id=%s", user.id)
            subs_with_links = []
        # Remember the address: it is also where a чек goes, and it is what makes
        # recovering access possible later without Telegram.
        await repo.update_user(user.id, email=email)

    chosen = next((u for sub, u in subs_with_links if sub.id == sub_id), None)
    if chosen is None and subs_with_links:
        chosen = subs_with_links[0][1]
    if not chosen:
        await message.answer(
            "Не нашли активную подписку. Откройте «🔌 Подключить VPN» ещё раз.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    text, body = _subscription_email_body(chosen)
    sent = await mailer.send_email(email, "Ваша ссылка UnLock VPN", text, html=body)
    if sent:
        await message.answer(
            f"📧 Отправили ссылку на <code>{html.escape(email)}</code>.\n\n"
            "Если письма нет — загляните в «Спам».",
            reply_markup=back_to_menu_keyboard(),
        )
    else:
        # Never claim delivery we did not achieve: the whole point is that this
        # copy is reachable when Telegram is not.
        await message.answer(
            "Не удалось отправить письмо. Попробуйте позже или напишите в поддержку.",
            reply_markup=back_to_menu_keyboard(),
        )
