import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.banners import EXPIRED_BANNER, send_banner
from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.texts import bq, format_msk
from config import settings
from database.models import Payment
from database.repository import Repository
from services.panel_gateway import (
    PanelGateway,
    PanelGatewayError,
    PanelUserNotFoundError,
    RemnawavePanelGateway,
    get_panel_gateway,
    is_panel_configured,
)
from services import yookassa
from services.alerts import send_alert
from services.money import format_rub
from services.payment import parse_invoice_payload_details
from services.qrcode import generate_qr_png_bytes
from services.subscription import (
    activate_panel_subscription,
    activate_subscription,
    connect_page_url,
    to_gateway_subscription_url,
)
from services.tariffs import resolve_tariff
from services.wireguard import WireGuardError, ensure_user_peer, remove_peer

logger = logging.getLogger(__name__)
PANEL_INACTIVE_STATUSES = {"DISABLED", "LIMITED", "EXPIRED"}


async def check_expiring_subscriptions(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(timezone.utc)
    async with session_pool() as session:
        repo = Repository(session)
        subscriptions = await repo.get_expiring_subscriptions(days=3)
        for subscription in subscriptions:
            if subscription.user.telegram_id <= 0:
                # Web email-only account (synthetic negative id) — no Telegram chat.
                await repo.mark_subscription_reminded(subscription.id)
                continue
            # A 3-day trial falls inside the 3-day window the moment it is
            # activated — greeting a fresh trial with «скоро закончится» is
            # absurd. Trials get one reminder on their LAST day instead.
            is_trial = subscription.tier == "trial"
            if is_trial and _aware(subscription.expires_at) - now > timedelta(days=1):
                continue  # not marked — revisited when the last day comes
            if is_trial:
                text = (
                    "⏰ <b>Пробный период заканчивается сегодня</b>\n\n"
                    "Понравилось? Оформите тариф — ссылка-подписка останется той же, "
                    "ничего перенастраивать не придётся. Кнопка «🛒 Купить подписку» в меню."
                )
            else:
                text = (
                    "⏰ <b>Подписка скоро закончится</b>\n\n"
                    + bq("📅 Осталось: меньше 3 дней")
                    + "\n\nЧтобы не потерять доступ, продлите подписку — кнопка «🔄 Продлить» в меню."
                )
            try:
                await bot.send_message(chat_id=subscription.user.telegram_id, text=text)
                await repo.mark_subscription_reminded(subscription.id)
            except Exception:
                logger.exception("Failed to send expiration reminder for subscription_id=%s", subscription.id)


async def deactivate_expired_subscriptions(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        subscriptions = await repo.get_expired_active_subscriptions()
        panel = get_panel_gateway() if is_panel_configured() else None
        for subscription in subscriptions:
            key = await repo.get_wireguard_key_by_user_id(subscription.user_id)
            if key is not None:
                try:
                    await remove_peer(key.public_key)
                except WireGuardError:
                    logger.exception("Failed to remove WireGuard peer for user_id=%s", subscription.user_id)

            if subscription.tier == "premium":
                try:
                    await release_subscription_nodes(session, subscription.id)
                except Exception:
                    logger.exception("Failed to release premium nodes for subscription_id=%s", subscription.id)

            await repo.deactivate_subscription(subscription.id)
            notify_chat_id = (
                subscription.user.telegram_id if subscription.user.telegram_id > 0 else None
            )

            if panel is not None and subscription.panel_username:
                # A renewal keeps the same panel user under a newer, still
                # active row — cutting panel access then would kick a payer.
                still_used = any(
                    s.panel_username == subscription.panel_username
                    for s in await repo.list_active_panel_subscriptions()
                )
                if not still_used:
                    try:
                        await panel.modify_user(
                            username=subscription.panel_username,
                            expire_at=subscription.expires_at,
                            status="disabled",
                        )
                    except PanelUserNotFoundError:
                        pass
                    except PanelGatewayError:
                        logger.exception(
                            "Failed to disable panel user %s for subscription_id=%s",
                            subscription.panel_username,
                            subscription.id,
                        )
            if notify_chat_id is None:
                continue
            try:
                await send_banner(
                    bot,
                    notify_chat_id,
                    EXPIRED_BANNER,
                    caption=(
                        "⛔️ <b>Подписка истекла</b>\n\n"
                        "Доступ отключён. Верните его в один тап — ссылка-подписка останется прежней."
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🔄 Продлить", callback_data="renew_menu")]
                        ]
                    ),
                )
            except Exception:
                logger.exception("Failed to notify expired subscription user_id=%s", subscription.user_id)


async def traffic_sync(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
    panel_client: object | None = None,
    panel_gateway: PanelGateway | None = None,
) -> int:
    if panel_gateway is not None and panel_client is not None:
        raise ValueError("panel_gateway and panel_client are mutually exclusive")
    if panel_client is None and panel_gateway is None and not _remnawave_configured():
        return 0

    client = panel_gateway or (RemnawavePanelGateway(panel_client) if panel_client is not None else get_panel_gateway())
    synced_count = 0
    async with session_pool() as session:
        repo = Repository(session)
        subscriptions = await repo.list_active_panel_subscriptions()
        # Subscriptions the traffic cap parked are inactive by definition, so
        # the query above never returns them. Without this they stay dead for
        # the rest of a paid term even after the panel refills the allowance.
        subscriptions += await repo.list_traffic_limited_subscriptions()
        for subscription in subscriptions:
            if not subscription.panel_username:
                continue

            try:
                panel_user = await client.get_user(subscription.panel_username)
            except PanelUserNotFoundError:
                await repo.update_subscription(subscription.id, status="not_found", is_active=False)
                synced_count += 1
                try:
                    await bot.send_message(
                        chat_id=subscription.user.telegram_id,
                        text=(
                            "⚠️ <b>Проблема с подпиской</b>\n\n"
                            "Подписка не найдена в панели. Обратитесь в поддержку."
                        ),
                    )
                except Exception:
                    logger.exception("Failed to notify missing panel user subscription_id=%s", subscription.id)
                continue
            except PanelGatewayError:
                logger.exception("Failed to sync panel usage for subscription_id=%s", subscription.id)
                continue

            traffic_limit_bytes = subscription.traffic_limit_bytes
            if traffic_limit_bytes is None:
                traffic_limit_bytes = panel_user.traffic_limit_bytes

            status = panel_user.status.upper()
            used_traffic_bytes = panel_user.used_traffic_bytes
            should_deactivate = status in PANEL_INACTIVE_STATUSES
            if traffic_limit_bytes is not None and used_traffic_bytes >= traffic_limit_bytes:
                should_deactivate = True
                status = "LIMITED"

            had_no_traffic = (subscription.traffic_used_bytes or 0) == 0
            was_parked = not subscription.is_active
            await repo.update_subscription(
                subscription.id,
                status=status.lower(),
                is_active=not should_deactivate,
                traffic_used_bytes=used_traffic_bytes,
                traffic_limit_bytes=traffic_limit_bytes,
                device_limit=panel_user.device_limit,
                subscription_url=panel_user.subscription_url,
                sub_token=panel_user.short_uuid,
            )
            synced_count += 1

            # Funnel: the first bytes through the panel mean the user actually connected.
            if had_no_traffic and used_traffic_bytes > 0:
                await repo.record_funnel_event(subscription.user_id, "first_connect")

            if was_parked and not should_deactivate:
                try:
                    await bot.send_message(
                        chat_id=subscription.user.telegram_id,
                        text=(
                            "✅ <b>Трафик обновлён</b>\n\n"
                            + bq("📊 Месячная квота начислена заново — подписка снова работает")
                        ),
                    )
                except Exception:
                    logger.exception("Failed to notify revived subscription_id=%s", subscription.id)

            if should_deactivate:
                if subscription.tier == "premium":
                    try:
                        await release_subscription_nodes(session, subscription.id)
                    except Exception:
                        logger.exception("Failed to release premium nodes for subscription_id=%s", subscription.id)
                try:
                    await bot.send_message(
                        chat_id=subscription.user.telegram_id,
                        text=(
                            "⛔️ <b>Подписка остановлена</b>\n\n"
                            + bq("📊 Причина: закончился трафик или доступ отключён")
                            + "\n\nПродлите тариф или обратитесь в поддержку."
                        ),
                    )
                except Exception:
                    logger.exception("Failed to notify limited subscription_id=%s", subscription.id)

    return synced_count


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _access_text(expires_at: datetime) -> str:
    return (
        "✅ Оплата получена!\n"
        f"Подписка активна до {_aware(expires_at):%d.%m.%Y %H:%M} UTC\n\n"
        "🔑 Ваш WireGuard-ключ (.conf файл прикреплён ниже)\n"
        "📸 QR-код для импорта — следующим сообщением\n\n"
        "📖 Как подключиться:\n"
        "1. Скачайте WireGuard:\n"
        "   • iOS: App Store\n"
        "   • Android: Google Play\n"
        "   • Windows/Mac: wireguard.com/install\n"
        "2. В приложении нажмите «+» → «Импорт из файла» или «Сканировать QR»\n"
        "3. Включите туннель — готово\n\n"
        f"Проблемы? {settings.support_contact}"
    )


def _remnawave_configured() -> bool:
    return is_panel_configured()


def _remnawave_api_configured() -> bool:
    return bool(settings.REMNAWAVE_API_URL.strip() and settings.remnawave_api_token.strip())




async def _send_access_bundle(bot: Bot, telegram_id: int, config_text: str, expires_at: datetime) -> None:
    qr_bytes = await generate_qr_png_bytes(config_text)
    await bot.send_message(chat_id=telegram_id, text=_access_text(expires_at))
    await bot.send_document(
        chat_id=telegram_id,
        document=BufferedInputFile(config_text.encode("utf-8"), filename=f"wireguard_{telegram_id}.conf"),
        caption="WireGuard-конфиг для UnLock.",
    )
    await bot.send_photo(
        chat_id=telegram_id,
        photo=BufferedInputFile(qr_bytes, filename="wireguard_qr.png"),
        caption="QR-код для импорта в WireGuard.",
        reply_markup=back_to_menu_keyboard(),
    )


def _subscription_access_text(subscription_url: str, expires_at: datetime) -> str:
    return (
        "🎉 <b>Оплата получена!</b>\n\n"
        + bq(f"📅 Активна до: {format_msk(expires_at)}")
        + "\n\n🔗 <b>Ссылка-подписка:</b>\n"
        f"<code>{subscription_url}</code>\n\n"
        "Нажмите «Подключить VPN» — откроется страница с приложениями и пошаговой инструкцией."
        + f"\n\nПроблемы? {settings.support_contact}"
    )


async def _send_subscription_bundle(
    bot: Bot,
    telegram_id: int,
    subscription_url: str,
    expires_at: datetime,
) -> None:
    # Deliver the link + a button to the /connect setup page — no QR image.
    connect_url = connect_page_url(subscription_url)
    if connect_url:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Подключить VPN", url=connect_url)],
                [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
            ]
        )
    else:
        keyboard = back_to_menu_keyboard()
    await bot.send_message(
        chat_id=telegram_id,
        text=_subscription_access_text(
            subscription_url,
            expires_at,
        ),
        reply_markup=keyboard,
    )


async def check_inbound_drift() -> None:
    """Warn when the panel serves inbounds that new accounts never receive.

    MARZBAN_DEFAULT_INBOUNDS is written by hand, so every inbound added to the
    panel has to be copied into it by hand too. On 2026-08-10 that copy had been
    missed for Germany and for every XHTTP transport, and the seven accounts
    opened over the previous week were issued the three oldest tags — one of them
    pointing at a node that no longer answers. Nothing surfaced it: those
    accounts looked healthy, they were simply given less than they paid for.

    Only protocols the defaults already mention are compared. Trojan and
    Hysteria2 are attached to subscriptions by the gateway itself, so their
    absence here is deliberate rather than drift.
    """
    gateway = get_panel_gateway()
    if getattr(gateway, "provider", None) != "marzban":
        return

    defaults = settings.marzban_default_inbounds_dict
    if not defaults:
        return

    try:
        panel_inbounds = await gateway.client.get_inbounds()
    except Exception:
        logger.exception("Inbound drift check failed to read the panel")
        return

    missing: list[str] = []
    for protocol, configured in defaults.items():
        known = set(configured)
        for inbound in panel_inbounds.get(protocol) or []:
            tag = inbound.get("tag")
            if tag and tag not in known:
                missing.append(tag)

    # The check above compares the panel against our configuration, which only
    # catches a configuration that was never updated. On 2026-08-19 the
    # configuration was right and customers were still short-changed: the API
    # process serving the website had been started five hours before the file
    # was edited and kept issuing the old three tags for nine days, to six
    # paying customers. So the accounts themselves are audited too — that is the
    # thing we actually promise, and it is wrong no matter which layer broke.
    short: list[str] = []
    try:
        for user in await gateway.client.list_users():
            if user.get("status") != "active":
                continue
            held = {tag for tags in (user.get("inbounds") or {}).values() for tag in tags}
            if any(set(tags) - held for tags in defaults.values()):
                short.append(str(user.get("username")))
    except Exception:
        logger.exception("Inbound drift check could not audit accounts")

    if short:
        logger.warning("Accounts issued fewer inbounds than configured: %s", ", ".join(short[:20]))
        await send_alert(
            "⚠️ У части активных подписок меньше инбаундов, чем задано в настройке.\n\n"
            f"Затронуто аккаунтов: {len(short)}\n"
            + "\n".join(f"• {name}" for name in short[:10])
            + ("\n…" if len(short) > 10 else "")
            + "\n\nОбычно это служба, запущенная до правки .env — перезапустите "
            "unlock-api и unlock-vpnbot, затем выровняйте аккаунты.",
            throttle_key="inbound_short_accounts",
            cooldown=86400.0,
        )

    if not missing:
        return

    logger.warning("Inbound drift: new accounts would not receive %s", ", ".join(sorted(missing)))
    await send_alert(
        "⚠️ Новые подписки выдаются без части инбаундов.\n\n"
        "Панель отдаёт, а MARZBAN_DEFAULT_INBOUNDS не содержит:\n"
        + "\n".join(f"• {tag}" for tag in sorted(missing))
        + "\n\nДобавьте их в .env и выровняйте уже заведённых пользователей.",
        throttle_key="inbound_drift",
        cooldown=86400.0,
    )


# What each provider calls a checkout the buyer walked away from.
DEAD_PAYMENT_STATUSES = {"canceled", "cancelled", "expired", "failed"}
# ...and what it calls one that went through.
PAID_PAYMENT_STATUSES = {"succeeded", "paid"}


def _payment_amount_text(payment: Payment) -> str:
    """Amounts are stored in the minor unit of whatever the provider charged —
    kopecks for YooKassa, and older CryptoBot rows hold USDT cents — so only
    rouble rows may go through the rouble formatter."""
    if (payment.currency or "").upper() == "RUB":
        return format_rub(payment.amount)
    return f"{payment.amount / 100:.2f} {payment.currency}"


async def _stale_payment_verdict(payment: Payment) -> str | None:
    """Ask the provider what really became of one pending checkout.

    Returns the provider's status string, or None when we could not find out.
    """
    external_id = str(payment.external_invoice_id or "")
    if not external_id:
        return None

    if payment.provider == "yookassa":
        remote = await yookassa.get_payment(external_id)
        return str(remote.get("status") or "")

    return None


async def reconcile_stale_payments(session_pool: async_sessionmaker[AsyncSession]) -> None:
    """Close the books on checkouts that never came back.

    Providers cancel an abandoned checkout on their side and never tell us, so
    the row sits pending forever and every revenue and funnel number counts it
    as money in flight. Once a checkout is too old to still be live we ask the
    provider directly and write down the real answer.

    A pending row the provider reports as PAID is the opposite problem: the
    buyer's money moved and our webhook never landed. That row is left alone
    and escalated — delivering it belongs to a human, not to a cleanup job.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.STALE_PAYMENT_HOURS)

    async with session_pool() as session:
        repo = Repository(session)
        stale = await repo.list_stale_pending_payments(older_than=cutoff)

        for payment in stale:
            try:
                status = await _stale_payment_verdict(payment)
            except Exception:
                # One unreachable provider must not stop the rest of the sweep.
                logger.exception(
                    "Could not reconcile payment id=%s provider=%s external_id=%s",
                    payment.id,
                    payment.provider,
                    payment.external_invoice_id,
                )
                continue

            if status is None:
                continue
            normalised = status.strip().lower()

            if normalised in PAID_PAYMENT_STATUSES:
                logger.error(
                    "Pending payment id=%s was actually PAID at %s (external_id=%s user_id=%s)",
                    payment.id,
                    payment.provider,
                    payment.external_invoice_id,
                    payment.user_id,
                )
                await send_alert(
                    "‼️ Оплата прошла, а подписка не выдана.\n\n"
                    f"Платёж #{payment.id} · пользователь {payment.user_id}\n"
                    f"{_payment_amount_text(payment)} · {payment.provider}\n"
                    f"Счёт: {payment.external_invoice_id}\n\n"
                    "Вебхук не дошёл. Выдайте доступ вручную.",
                    throttle_key=f"unpaid_delivery:{payment.id}",
                    cooldown=3600.0,
                )
                continue

            if normalised in DEAD_PAYMENT_STATUSES:
                await repo.update_payment_status(payment.id, "canceled")
                logger.info(
                    "Payment id=%s closed as canceled (%s said %s)",
                    payment.id,
                    payment.provider,
                    normalised,
                )


def setup_scheduler(bot: Bot, session_pool: async_sessionmaker[AsyncSession]) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(
        check_expiring_subscriptions,
        trigger="interval",
        hours=1,
        args=[bot, session_pool],
        id="check_expiring_subscriptions",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        deactivate_expired_subscriptions,
        trigger="interval",
        hours=1,
        args=[bot, session_pool],
        id="deactivate_expired_subscriptions",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        traffic_sync,
        trigger="interval",
        hours=1,
        args=[bot, session_pool],
        id="traffic_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        reconcile_stale_payments,
        trigger="interval",
        hours=1,
        args=[session_pool],
        id="reconcile_stale_payments",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        check_inbound_drift,
        trigger="interval",
        hours=6,
        id="check_inbound_drift",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    return scheduler
