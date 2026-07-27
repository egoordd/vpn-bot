import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.texts import bq, format_msk
from config import settings
from database.repository import Repository
from scheduler.tasks import traffic_sync
from services import wallet
from services.money import format_rub
from services.panel_gateway import PanelGatewayError, get_panel_gateway
from services.promo import PROMO_BALANCE_BONUS
from services.qrcode import generate_qr_png_bytes
from services.subscription import activate_subscription
from services.wireguard import WireGuardError, ensure_user_peer

logger = logging.getLogger(__name__)
router = Router()

TEST_KEY_PLAN = "standard_1m"


def _is_admin(message: Message) -> bool:
    return message.from_user.id in settings.admin_ids_list


async def _reject_non_admin(message: Message) -> bool:
    if _is_admin(message):
        return False
    await message.answer("Команда доступна только администраторам")
    return True


def _format_gb(value: int | None) -> str:
    if value is None:
        return "без лимита"
    return f"{value / 1024**3:.1f} ГБ"


def _parse_telegram_id_arg(message: Message) -> int:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        return message.from_user.id
    return int(parts[1].strip())


@router.message(Command("test_key"))
async def test_key_handler(
    message: Message,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    if await _reject_non_admin(message):
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        await activate_subscription(session=session, user_id=user.id, plan=TEST_KEY_PLAN)

        try:
            _, config_text = await ensure_user_peer(session=session, user_id=user.id)
        except WireGuardError:
            logger.exception("WireGuard provisioning failed for admin test_key user_id=%s", user.id)
            await message.answer("Не удалось подготовить ключ. Напишите в поддержку.")
            return

    qr_bytes = await generate_qr_png_bytes(config_text)
    filename = f"wireguard_{message.from_user.id}.conf"
    await message.answer_document(
        BufferedInputFile(config_text.encode("utf-8"), filename=filename),
        caption="Ваш WireGuard-конфиг.",
    )
    await message.answer_photo(
        BufferedInputFile(qr_bytes, filename="wireguard_qr.png"),
        caption="QR-код для импорта в WireGuard.",
    )


@router.message(Command("sync_traffic"))
async def sync_traffic_handler(
    message: Message,
    session_pool: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    if await _reject_non_admin(message):
        return

    try:
        synced_count = await traffic_sync(bot=bot, session_pool=session_pool)
    except Exception:
        logger.exception("Manual traffic sync failed")
        await message.answer("Не удалось синхронизировать трафик. Смотрите логи.")
        return

    await message.answer(f"Синхронизация трафика завершена. Обновлено подписок: {synced_count}.")


@router.message(Command("panel_user"))
async def panel_user_handler(
    message: Message,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    if await _reject_non_admin(message):
        return

    try:
        telegram_id = _parse_telegram_id_arg(message)
    except ValueError:
        await message.answer("Использование: /panel_user <telegram_id>")
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(telegram_id)
        if user is None:
            await message.answer(f"Пользователь {telegram_id} не найден в БД.")
            return
        subscription = await repo.get_latest_subscription(user.id)

    if subscription is None:
        await message.answer(f"У пользователя {telegram_id} нет подписок.")
        return
    if not subscription.panel_username:
        await message.answer(f"Последняя подписка пользователя {telegram_id} не привязана к панели.")
        return

    try:
        panel_user = await get_panel_gateway().get_user(subscription.panel_username)
    except PanelGatewayError:
        logger.exception(
            "Failed to fetch panel user for telegram_id=%s panel_username=%s",
            telegram_id,
            subscription.panel_username,
        )
        await message.answer("Не удалось получить пользователя из панели. Смотрите логи.")
        return

    text = (
        f"Telegram ID: {telegram_id}\n"
        f"Panel username: {panel_user.username}\n"
        f"Status: {panel_user.status}\n"
        f"Traffic: {_format_gb(panel_user.used_traffic_bytes)} / {_format_gb(panel_user.traffic_limit_bytes)}\n"
        f"Devices: {panel_user.device_limit or 'без лимита'}\n"
        f"Expires: {panel_user.expire_at}\n"
        f"Sub URL: {panel_user.subscription_url}"
    )
    await message.answer(text)


@router.message(Command("admin"))
async def admin_help_handler(message: Message) -> None:
    if await _reject_non_admin(message):
        return
    text = (
        "🛠 <b>Админ-команды</b>\n"
        + bq(
            "/stats — сводка по проекту",
            "/find &lt;tg_id&gt; — карточка пользователя",
            "/grant &lt;tg_id&gt; &lt;₽&gt; — начислить на баланс",
            "/gift_promo &lt;КОД&gt; &lt;₽&gt; [исп.] — промокод на баланс",
            "/sync_traffic — синхронизировать трафик",
            "/panel_user &lt;tg_id&gt; — юзер в панели",
            "/funnel — воронка start→триал→подключение→оплата",
        )
    )
    await message.answer(text)


@router.message(Command("stats"))
async def stats_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    if await _reject_non_admin(message):
        return
    async with session_pool() as session:
        repo = Repository(session)
        total_users = await repo.count_users()
        new_24h = await repo.count_users_since(datetime.now(timezone.utc) - timedelta(days=1))
        new_7d = await repo.count_users_since(datetime.now(timezone.utc) - timedelta(days=7))
        by_tier = await repo.count_active_subscriptions_by_tier()
        balances = await repo.sum_all_user_balances()
        spent = abs(await repo.sum_all_wallet_by_kind(wallet.KIND_SPEND))
        deposited = await repo.sum_all_wallet_by_kind(wallet.KIND_DEPOSIT)

    active_total = sum(by_tier.values())
    tier_lines = ", ".join(f"{tier}: {count}" for tier, count in sorted(by_tier.items())) or "нет"
    text = (
        "📊 <b>Статистика</b>\n\n"
        "👥 <b>Пользователи</b>\n"
        + bq(
            f"Всего: {total_users}",
            f"Новых за 24ч: {new_24h}",
            f"Новых за 7д: {new_7d}",
        )
        + "\n\n🔑 <b>Активные подписки</b>\n"
        + bq(f"Всего: {active_total}", f"По тарифам: {tier_lines}")
        + "\n\n💰 <b>Деньги</b>\n"
        + bq(
            f"На балансах: {format_rub(balances)}",
            f"Потрачено на тарифы: {format_rub(spent)}",
            f"Пополнено (CryptoBot): {format_rub(deposited)}",
        )
    )
    await message.answer(text)


FUNNEL_STEPS: tuple[tuple[str, str], ...] = (
    ("start", "Запустили бота"),
    ("trial", "Получили триал"),
    ("first_connect", "Подключились"),
    ("payment", "Оплатили"),
)


def _funnel_report(counts: dict[str, int], title: str) -> str:
    lines = []
    previous: int | None = None
    for event, label in FUNNEL_STEPS:
        count = counts.get(event, 0)
        if previous in (None, 0):
            lines.append(f"{label}: {count}")
        else:
            lines.append(f"{label}: {count} ({count * 100 // previous}% от пред.)")
        previous = count
    return f"<b>{title}</b>\n" + bq(*lines)


def _source_report(
    by_source: dict[str, dict[str, int]], clicks: dict[str, int] | None = None
) -> str:
    """Compact per-source funnel for each channel, biggest first.

    Starts with clicks on the /go/<campaign> link where we have them, so a
    channel that gets taps but no starts (bad landing, wrong audience) is
    visibly different from one nobody clicked at all. Campaigns with clicks but
    zero starts still get a row — that gap is exactly what needs fixing."""
    clicks = clicks or {}
    if not by_source and not clicks:
        return "<b>По источникам</b>\n" + bq("Пока нет данных.")
    names = set(by_source) | set(clicks)
    ordered = sorted(
        names,
        key=lambda name: (clicks.get(name, 0), by_source.get(name, {}).get("start", 0)),
        reverse=True,
    )
    lines = []
    for source in ordered:
        counts = by_source.get(source, {})
        starts = counts.get("start", 0)
        trials = counts.get("trial", 0)
        paid = counts.get("payment", 0)
        head = f"{clicks[source]} переход → " if source in clicks else ""
        lines.append(f"{source}: {head}{starts} старт → {trials} триал → {paid} оплат")
    return "<b>По источникам</b>\n" + bq(*lines)


@router.message(Command("funnel"))
async def funnel_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    if await _reject_non_admin(message):
        return
    async with session_pool() as session:
        repo = Repository(session)
        total = await repo.funnel_counts()
        week = await repo.funnel_counts(since=datetime.now(timezone.utc) - timedelta(days=7))
        by_source = await repo.source_funnel_counts()
        clicks = await repo.link_click_counts()

    text = (
        "🧭 <b>Воронка</b>\n\n"
        + _funnel_report(total, "За всё время")
        + "\n\n"
        + _funnel_report(week, "За 7 дней")
        + "\n\n"
        + _source_report(by_source, clicks)
        + "\n\n"
        + bq(
            "События пишутся один раз на пользователя; проценты — конверсия из предыдущего шага.",
            "Ссылка кампании: unlockvpn.site/go/ИМЯ — считает переходы и ведёт в бота.",
            "Прямая ссылка без счётчика переходов: t.me/unlkvpn_bot?start=src_ИМЯ.",
        )
    )
    await message.answer(text)


@router.message(Command("find"))
async def find_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    if await _reject_non_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer("Использование: /find &lt;telegram_id&gt;")
        return
    telegram_id = int(parts[1].strip())
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(telegram_id)
        if user is None:
            await message.answer(f"Пользователь {telegram_id} не найден.")
            return
        balance = await repo.get_balance(user.id) or 0
        subs = await repo.list_active_subscriptions(user.id)
        referrals = await repo.count_referrals(user.id)

    lines = [
        f"🆔 ID: <code>{user.telegram_id}</code>",
        f"👤 @{user.username}" if user.username else "👤 (без username)",
        f"💰 Баланс: {format_rub(balance)}",
        f"👥 Рефералов: {referrals}",
    ]
    sub_lines = [
        f"{'💎 Premium' if s.tier == 'premium' else '🌐 ' + s.tier}: до {format_msk(s.expires_at)}"
        for s in subs
    ] or ["нет активных"]
    text = "👤 <b>Пользователь</b>\n" + bq(*lines) + "\n\n🔑 <b>Подписки</b>\n" + bq(*sub_lines)
    await message.answer(text)


@router.message(Command("grant"))
async def grant_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    if await _reject_non_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
        await message.answer("Использование: /grant &lt;telegram_id&gt; &lt;рубли&gt;")
        return
    telegram_id, rubles = int(parts[1]), int(parts[2])
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(telegram_id)
        if user is None:
            await message.answer(f"Пользователь {telegram_id} не найден.")
            return
        entry = await wallet.deposit(
            session, user.id, rubles * 100,
            kind=wallet.KIND_ADJUSTMENT, description="Начисление администратором",
        )
    await message.answer(
        f"✅ Начислено {format_rub(rubles * 100)} пользователю {telegram_id}.\n"
        f"Новый баланс: {format_rub(entry.balance_after_kopecks)}"
    )


@router.message(Command("gift_promo"))
async def gift_promo_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    if await _reject_non_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 3 or not parts[2].isdigit():
        await message.answer("Использование: /gift_promo &lt;КОД&gt; &lt;рубли&gt; [макс_использований]")
        return
    code = parts[1].strip().upper()
    rubles = int(parts[2])
    max_uses = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
    async with session_pool() as session:
        repo = Repository(session)
        if await repo.get_promo_code(code) is not None:
            await message.answer(f"Промокод {code} уже существует.")
            return
        await repo.create_promo_code(
            code=code, kind=PROMO_BALANCE_BONUS, value=rubles * 100,
            max_uses=max_uses, per_user_limit=1, is_active=True,
            description=f"Промокод на {rubles}₽",
        )
    limit_txt = f"до {max_uses} активаций" if max_uses else "без лимита активаций"
    await message.answer(f"✅ Промокод <code>{code}</code> на {format_rub(rubles * 100)} создан ({limit_txt}).")
