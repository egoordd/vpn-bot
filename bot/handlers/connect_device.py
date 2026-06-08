import html
import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from database.repository import Repository
from services.deeplinks import AppImportGuide, build_app_import_guides
from services.panel_gateway import PanelGatewayError, get_panel_gateway
from services.qrcode import generate_qr_png_bytes
from services.wireguard import WireGuardError, rotate_user_key

logger = logging.getLogger(__name__)
router = Router()

APP_CODES = {"hiddify", "v2raytun", "streisand", "singbox"}


def _connect_device_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Hiddify", callback_data="connect_app:hiddify"),
                InlineKeyboardButton(text="V2RayTun", callback_data="connect_app:v2raytun"),
            ],
            [
                InlineKeyboardButton(text="Streisand", callback_data="connect_app:streisand"),
                InlineKeyboardButton(text="sing-box", callback_data="connect_app:singbox"),
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def _app_instruction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К подключению", callback_data="connect_device")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")],
        ]
    )


def _subscription_access_text(subscription_url: str) -> str:
    escaped_url = html.escape(subscription_url)
    return (
        "<b>Подключение устройства</b>\n\n"
        "Ссылка-подписка:\n"
        f"<code>{escaped_url}</code>\n\n"
        "Выберите приложение ниже. Если быстрый импорт не сработает, "
        "скопируйте ссылку или отсканируйте QR-код."
    )


def _app_instruction_text(guide: AppImportGuide, subscription_url: str) -> str:
    escaped_url = html.escape(subscription_url)
    lines = [f"<b>{html.escape(guide.title)}</b>", ""]
    if guide.deeplink:
        lines.extend(["Быстрый импорт:", f"<code>{html.escape(guide.deeplink)}</code>", ""])
    lines.append("Если быстрый импорт не открыл приложение:")
    for index, step in enumerate(guide.steps, start=1):
        lines.append(f"{index}. {html.escape(step)}")
    lines.extend(["", "Ссылка-подписка:", f"<code>{escaped_url}</code>"])
    return "\n".join(lines)


async def _resolve_subscription_url(repo: Repository, user_id: int) -> str | None:
    subscription = await repo.get_active_subscription(user_id)
    if subscription is None or not subscription.panel_username:
        return None
    if subscription.subscription_url:
        return subscription.subscription_url

    panel_user = await get_panel_gateway().get_user(subscription.panel_username)
    return panel_user.subscription_url


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
    user_id, subscription_url = await _get_user_and_subscription_url(callback, session_pool)
    if user_id is None:
        return

    if subscription_url:
        qr_bytes = await generate_qr_png_bytes(subscription_url)
        if callback.message:
            await callback.message.answer_photo(
                BufferedInputFile(qr_bytes, filename="subscription_qr.png"),
                caption=_subscription_access_text(subscription_url),
                reply_markup=_connect_device_keyboard(),
            )
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


@router.callback_query(F.data.startswith("connect_app:"), flags={"subscription_required": True})
async def connect_app_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    app_code = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    if app_code not in APP_CODES:
        await callback.answer("Приложение не найдено", show_alert=True)
        return

    _, subscription_url = await _get_user_and_subscription_url(callback, session_pool)
    if not subscription_url:
        await callback.answer("Для этой подписки доступен WireGuard-конфиг, а не ссылка-подписка.", show_alert=True)
        return

    guide = build_app_import_guides(subscription_url)[app_code]
    text = _app_instruction_text(guide, subscription_url)
    if callback.message:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=_app_instruction_keyboard())
        else:
            await callback.message.edit_text(text, reply_markup=_app_instruction_keyboard())
    await callback.answer()
