import html
import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq, format_msk
from services.tariffs import resolve_tariff
from config import settings
from database.models import Subscription
from database.repository import Repository
from services import node_probe
from services.awg_provision import AwgProvisionError, ensure_client_configs
from services.panel_gateway import PanelGatewayError, get_panel_gateway
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


def _awg_available() -> bool:
    return bool(settings.awg_nodes_dict)


def _connect_device_keyboard(
    happ_url: str | None = None,
    sub_id: int | None = None,
    site_url: str | None = None,
) -> InlineKeyboardMarkup:
    suffix = f":{sub_id}" if sub_id is not None else ""
    rows: list[list[InlineKeyboardButton]] = []
    if site_url:
        rows.append([InlineKeyboardButton(text="🔗 Подключить VPN", url=site_url)])
    if happ_url:
        rows.append([InlineKeyboardButton(text="📲 Импорт в Happ (выбор вручную)", url=happ_url)])
    rows.append([InlineKeyboardButton(text="🆘 Не подключается?", callback_data=f"connect_fix{suffix}")])
    if _awg_available():
        rows.append([InlineKeyboardButton(text="🔒 AmneziaWG (запасной канал)", callback_data="connect_awg")])
    rows.append([InlineKeyboardButton(text="❓ Как подключить вручную", callback_data=f"connect_help{suffix}")])
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _troubleshoot_keyboard(sub_id: int | None) -> InlineKeyboardMarkup:
    back = f"connect_loc:{sub_id}" if sub_id is not None else "connect_device"
    rows: list[list[InlineKeyboardButton]] = []
    if _awg_available():
        rows.append([InlineKeyboardButton(text="🔒 Включить AmneziaWG (запасной)", callback_data="connect_awg")])
    rows.append([InlineKeyboardButton(text="✍️ Написать в поддержку", url=_support_url())])
    rows.append([InlineKeyboardButton(text="◀️ К подключению", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _support_url() -> str:
    contact = settings.support_contact.lstrip("@")
    return f"https://t.me/{contact}" if contact and contact != "не указан" else "https://t.me/unlock_support_bot"


def _health_line(locations: list[node_probe.LocationHealth]) -> str | None:
    if not locations:
        return None
    parts = [
        f"{loc.flag} {loc.name} {'✅' if loc.reachable else '❌'}".strip()
        for loc in locations
    ]
    up = [loc for loc in locations if loc.reachable]
    if up:
        return "Сейчас доступны:\n" + " · ".join(parts)
    return "Похоже, серверы сейчас не отвечают:\n" + " · ".join(parts)


def _troubleshoot_text(locations: list[node_probe.LocationHealth]) -> str:
    up = [loc for loc in locations if loc.reachable]
    steps = [
        "1️⃣ В приложении выберите <b>другую страну</b>"
        + (f" из рабочих ({', '.join(loc.flag for loc in up)})" if up else "")
        + " и нажмите «Подключить».",
        "2️⃣ На мобильном интернете выбирайте сервер с пометкой <b>Hysteria2</b> — "
        "он лучше проходит блокировки операторов.",
        "3️⃣ Выключите и снова включите туннель; в приложении нажмите «Обновить подписку».",
        "4️⃣ Не помогло — включите запасной канал AmneziaWG или напишите в поддержку.",
    ]
    health = _health_line(locations)
    header = "🆘 <b>Не подключается? Разберёмся за минуту</b>"
    body = (f"{header}\n\n{health}\n\n" if health else f"{header}\n\n") + bq(*steps)
    return body


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
    escaped_url = html.escape(subscription_url)
    header = "📱 <b>Подключение устройства</b>"
    if location:
        header += f"\n{location}"
    return (
        f"{header}\n\n"
        "🔗 <b>Ссылка-подписка:</b>\n"
        f"<code>{escaped_url}</code>\n\n"
        + bq(
            "🔗 «Подключить VPN» — откроется страница, где всё делается в пару",
            "касаний: установка приложения и импорт подписки со всеми серверами.",
        )
        + "\n\n📲 Happ уже установлен? «Импорт в Happ» добавит подписку сразу.\n"
        "🌍 В списке будут все страны (🇺🇸 🇳🇱 🇵🇱) и протоколы — выберите любой сервер.\n"
        "❓ Другое приложение? Нажмите «Как подключить вручную».\n"
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
    # Text-only screen: the link + buttons cover every path (site page with
    # apps and «Авто-обход», direct Happ import) — no QR image is pushed.
    await show_screen(
        callback,
        _subscription_access_text(url, _location_label(subscription)),
        _connect_device_keyboard(
            to_happ_import_url(url),
            subscription.id,
            site_url=connect_page_url(url),
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


@router.callback_query(F.data.startswith("connect_fix"), flags={"subscription_required": True})
async def connect_troubleshoot_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    parts = callback.data.split(":") if callback.data else []
    sub_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    await callback.answer("Проверяю серверы…")

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        if user is None:
            await _send_processing_error(callback, "Пользователь не найден. Нажмите /start.")
            return
        subscription_url: str | None = None
        try:
            if sub_id is not None:
                subscription = await repo.get_subscription(sub_id)
                if subscription and subscription.user_id == user.id:
                    subscription_url = await _resolve_url_for_subscription(repo, subscription)
            if subscription_url is None:
                subscription_url = await _resolve_subscription_url(repo, user.id)
        except PanelGatewayError:
            logger.exception("Could not resolve subscription URL for troubleshoot, user_id=%s", user.id)
            subscription_url = None

    # Live reachability of the user's own servers (best-effort; empty on error).
    locations = await node_probe.probe_subscription(subscription_url or "")
    await show_screen(callback, _troubleshoot_text(locations), _troubleshoot_keyboard(sub_id))


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


_AWG_INTRO = (
    "🔒 <b>AmneziaWG — запасной канал</b>\n\n"
    + bq(
        "Отдельный протокол на случай, если основной где-то не проходит.",
        "Нужно приложение AmneziaVPN (App Store / Google Play).",
        "Импортируйте файл .conf или отсканируйте QR — по одному на страну.",
    )
)


@router.callback_query(F.data == "connect_awg", flags={"subscription_required": True})
async def connect_awg_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer("🔒 Готовлю конфиги AmneziaWG — несколько секунд…")

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        if user is None:
            await _send_processing_error(callback, "Пользователь не найден. Нажмите /start.")
            return
        try:
            configs = await ensure_client_configs(session, user.id)
        except AwgProvisionError:
            logger.exception("AmneziaWG provisioning failed for user_id=%s", user.id)
            await _send_processing_error(callback, "Не удалось подготовить AmneziaWG. Напишите в поддержку.")
            return

    if not configs:
        await _send_processing_error(callback, "AmneziaWG сейчас недоступен.")
        return

    if not callback.message:
        return

    await callback.message.answer(_AWG_INTRO)
    for cfg in configs:
        label = f"{cfg.flag} {cfg.name}".strip()
        await callback.message.answer_document(
            BufferedInputFile(cfg.config_text.encode("utf-8"), filename=f"unlock-awg-{cfg.node_code}.conf"),
            caption=f"{label} — AmneziaWG",
        )
        qr_bytes = await generate_qr_png_bytes(cfg.config_text)
        await callback.message.answer_photo(
            BufferedInputFile(qr_bytes, filename=f"awg-{cfg.node_code}.png"),
            caption=f"QR · {label}",
        )
    await callback.message.answer(
        "Готово. Импортируйте конфиг в приложение AmneziaVPN — и подключайтесь.",
        reply_markup=back_to_menu_keyboard(),
    )
