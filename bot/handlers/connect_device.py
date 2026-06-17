import html
import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq
from database.models import Subscription
from database.repository import Repository
from services.deeplinks import AppImportGuide, build_app_import_guides
from services.panel_gateway import PanelGatewayError, get_panel_gateway
from services.qrcode import generate_qr_png_bytes
from services.subscription import to_gateway_subscription_url
from services.wireguard import WireGuardError, rotate_user_key

logger = logging.getLogger(__name__)
router = Router()

APP_CODES = {"hiddify", "v2raytun", "streisand", "singbox"}


def _location_label(subscription: Subscription) -> str:
    if subscription.tier == "premium":
        return "💎 Premium"
    return "🌐 Обычный"


def _connect_device_keyboard(sub_id: int | None = None) -> InlineKeyboardMarkup:
    suffix = f":{sub_id}" if sub_id is not None else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Hiddify", callback_data=f"connect_app:hiddify{suffix}"),
                InlineKeyboardButton(text="V2RayTun", callback_data=f"connect_app:v2raytun{suffix}"),
            ],
            [
                InlineKeyboardButton(text="Streisand", callback_data=f"connect_app:streisand{suffix}"),
                InlineKeyboardButton(text="sing-box", callback_data=f"connect_app:singbox{suffix}"),
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def _location_selector_keyboard(subs: list[Subscription]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_location_label(sub), callback_data=f"connect_loc:{sub.id}")]
        for sub in subs
    ]
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _app_instruction_keyboard(sub_id: int | None = None) -> InlineKeyboardMarkup:
    back = f"connect_loc:{sub_id}" if sub_id is not None else "connect_device"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К подключению", callback_data=back)],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
        ]
    )


def _subscription_access_text(subscription_url: str, location: str | None = None) -> str:
    escaped_url = html.escape(subscription_url)
    header = "📱 <b>Подключение устройства</b>"
    if location:
        header += f"\n{location}"
    return (
        f"{header}\n\n"
        "🔗 <b>Ссылка-подписка:</b>\n"
        f"<code>{escaped_url}</code>\n\n"
        + bq(
            "1️⃣ Выберите приложение ниже",
            "2️⃣ Импортируйте ссылку (или отсканируйте QR)",
            "3️⃣ Включите туннель — готово",
        )
        + "\n\n🌍 В подписке несколько стран — выбирайте сервер в приложении.\n"
        "♻️ Сменили тариф или локацию? Нажмите «Обновить подписку» в приложении."
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
    qr_bytes = await generate_qr_png_bytes(url)
    if callback.message:
        await callback.message.answer_photo(
            BufferedInputFile(qr_bytes, filename="subscription_qr.png"),
            caption=_subscription_access_text(url, _location_label(subscription)),
            reply_markup=_connect_device_keyboard(subscription.id),
        )


def _app_instruction_text(guide: AppImportGuide, subscription_url: str) -> str:
    escaped_url = html.escape(subscription_url)
    lines = [f"📲 <b>{html.escape(guide.title)}</b>", ""]
    if guide.deeplink:
        lines.extend(["⚡️ <b>Быстрый импорт:</b>", f"<code>{html.escape(guide.deeplink)}</code>", ""])
    steps = [f"{index}. {html.escape(step)}" for index, step in enumerate(guide.steps, start=1)]
    lines.append("Если быстрый импорт не открыл приложение:")
    lines.append(bq(*steps))
    lines.extend(["", "🔗 <b>Ссылка-подписка:</b>", f"<code>{escaped_url}</code>"])
    return "\n".join(lines)


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
        try:
            subs_with_links = await _active_subs_with_links(repo, user_id)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URLs for user_id=%s", user_id)
            await callback.answer("Не удалось получить ссылку-подписку. Напишите в поддержку.", show_alert=True)
            return

    if len(subs_with_links) > 1:
        subs = [sub for sub, _ in subs_with_links]
        text = (
            "📱 <b>Подключение устройства</b>\n\n"
            "У вас несколько подписок. Выберите, какую подключить:"
        )
        await show_screen(callback, text, _location_selector_keyboard(subs))
        await callback.answer()
        return

    if len(subs_with_links) == 1:
        subscription, url = subs_with_links[0]
        await _send_subscription_screen(callback, subscription, url)
        await callback.answer()
        return

    async with session_pool() as session:
        try:
            _, config_text = await rotate_user_key(session=session, user_id=user_id)
        except WireGuardError:
            logger.exception("Could not provide WireGuard key for user_id=%s", user_id)
            await callback.answer("Не удалось подготовить ключ. Напишите в поддержку.", show_alert=True)
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
    await callback.answer()


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
        try:
            url = await _resolve_url_for_subscription(repo, subscription)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URL for sub_id=%s", sub_id)
            await callback.answer("Не удалось получить ссылку. Напишите в поддержку.", show_alert=True)
            return
    if not url:
        await callback.answer("Для этой подписки нет ссылки.", show_alert=True)
        return
    await _send_subscription_screen(callback, subscription, url)
    await callback.answer()


@router.callback_query(F.data.startswith("connect_app:"), flags={"subscription_required": True})
async def connect_app_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    parts = callback.data.split(":") if callback.data else []
    app_code = parts[1] if len(parts) > 1 else ""
    sub_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    if app_code not in APP_CODES:
        await callback.answer("Приложение не найдено", show_alert=True)
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        if user is None:
            await callback.answer("Пользователь не найден. Нажмите /start.", show_alert=True)
            return
        try:
            if sub_id is not None:
                subscription = await repo.get_subscription(sub_id)
                subscription_url = (
                    await _resolve_url_for_subscription(repo, subscription)
                    if subscription and subscription.user_id == user.id
                    else None
                )
            else:
                subscription_url = await _resolve_subscription_url(repo, user.id)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URL for user_id=%s", user.id)
            await callback.answer("Не удалось получить ссылку. Напишите в поддержку.", show_alert=True)
            return

    if not subscription_url:
        await callback.answer("Для этой подписки доступен WireGuard-конфиг, а не ссылка-подписка.", show_alert=True)
        return

    guide = build_app_import_guides(subscription_url)[app_code]
    text = _app_instruction_text(guide, subscription_url)
    if callback.message:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=_app_instruction_keyboard(sub_id))
        else:
            await callback.message.edit_text(text, reply_markup=_app_instruction_keyboard(sub_id))
    await callback.answer()
