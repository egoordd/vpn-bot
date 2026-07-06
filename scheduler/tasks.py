import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.banners import EXPIRED_BANNER, send_banner
from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.texts import bq, format_msk
from config import settings
from database.repository import Repository
from services.autoscaler import (
    AutoscalePoolResult,
    ProvisionNodeRequest,
    assign_subscription_to_node,
    autoscale_premium_pool,
    release_subscription_nodes,
)
from services.cryptobot import get_invoices_by_status
from services.panel_gateway import (
    PanelGateway,
    PanelGatewayError,
    PanelUserNotFoundError,
    RemnawavePanelGateway,
    get_panel_gateway,
    is_panel_configured,
)
from services import wallet
from services.money import format_rub
from services.payment import ParsedTopupPayload, parse_invoice_payload_details, parse_topup_payload
from services.qrcode import generate_qr_png_bytes
from services.referral import reward_referrer_for_payment
from services.subscription import (
    activate_panel_subscription,
    activate_subscription,
    to_gateway_subscription_url,
)
from services.tariffs import resolve_premium_region, resolve_tariff
from services.wireguard import WireGuardError, ensure_user_peer, remove_peer

logger = logging.getLogger(__name__)
PANEL_INACTIVE_STATUSES = {"DISABLED", "LIMITED", "EXPIRED"}


async def check_expiring_subscriptions(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        subscriptions = await repo.get_expiring_subscriptions(days=3)
        for subscription in subscriptions:
            try:
                await bot.send_message(
                    chat_id=subscription.user.telegram_id,
                    text=(
                        "⏰ <b>Подписка скоро закончится</b>\n\n"
                        + bq("📅 Осталось: меньше 3 дней")
                        + "\n\nЧтобы не потерять доступ, продлите подписку — кнопка «🔄 Продлить» в меню."
                    ),
                )
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
            try:
                await send_banner(
                    bot,
                    subscription.user.telegram_id,
                    EXPIRED_BANNER,
                    caption=(
                        "⛔️ <b>Подписка истекла</b>\n\n"
                        "Доступ отключён. Верни его в один тап — ссылка-подписка останется прежней."
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
        "🔑 Твой WireGuard-ключ (.conf файл прикреплён ниже)\n"
        "📸 QR-код для импорта — следующим сообщением\n\n"
        "📖 Как подключиться:\n"
        "1. Скачай WireGuard:\n"
        "   • iOS: App Store\n"
        "   • Android: Google Play\n"
        "   • Windows/Mac: wireguard.com/install\n"
        "2. В приложении нажми «+» → «Импорт из файла» или «Сканировать QR»\n"
        "3. Включи туннель — готово\n\n"
        f"Проблемы? {settings.support_contact}"
    )


def _remnawave_configured() -> bool:
    return is_panel_configured()


def _remnawave_api_configured() -> bool:
    return bool(settings.REMNAWAVE_API_URL.strip() and settings.remnawave_api_token.strip())


def _autoscaler_configured() -> bool:
    return bool(
        _remnawave_api_configured()
        and settings.vultr_api_token.strip()
        and settings.VULTR_DEFAULT_OS_ID
        and settings.REMNAWAVE_NODE_CONFIG_PROFILE_UUID.strip()
        and settings.remnawave_node_inbound_uuids_list
    )


async def autoscale_check(
    session_pool: async_sessionmaker[AsyncSession],
    *,
    regions: list[str] | None = None,
    min_free_slots: int | None = None,
    min_active_nodes: int | None = None,
    max_provisions_per_region: int | None = None,
    decommission_empty: bool | None = None,
) -> AutoscalePoolResult:
    regions_to_check = regions if regions is not None else settings.autoscale_premium_regions_list
    result = AutoscalePoolResult(checked_regions=len(regions_to_check))
    if not regions_to_check:
        return result
    if regions is None and not _autoscaler_configured():
        logger.info("Autoscale check skipped: autoscaler external settings are incomplete")
        return result

    async with session_pool() as session:
        try:
            return await autoscale_premium_pool(
                session,
                regions=regions_to_check,
                min_free_slots=(
                    settings.AUTOSCALE_PREMIUM_MIN_FREE_SLOTS
                    if min_free_slots is None
                    else min_free_slots
                ),
                min_active_nodes=(
                    settings.AUTOSCALE_PREMIUM_MIN_ACTIVE_NODES
                    if min_active_nodes is None
                    else min_active_nodes
                ),
                max_provisions_per_region=(
                    settings.AUTOSCALE_MAX_PROVISIONS_PER_REGION
                    if max_provisions_per_region is None
                    else max_provisions_per_region
                ),
                decommission_empty=(
                    settings.AUTOSCALE_DECOMMISSION_EMPTY
                    if decommission_empty is None
                    else decommission_empty
                ),
            )
        except Exception:
            logger.exception("Autoscale check failed")
            return result


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


def _subscription_access_text(
    subscription_url: str,
    expires_at: datetime,
    *,
    premium_region_title: str | None = None,
) -> str:
    card_lines = [f"📅 Активна до: {format_msk(expires_at)}"]
    if premium_region_title:
        card_lines.append(f"🌍 Локация: {premium_region_title}")
    note = (
        "\n\n⏳ Если сервер только поднят, клиент увидит обновление в течение ~2 минут."
        if premium_region_title
        else ""
    )
    return (
        "🎉 <b>Оплата получена!</b>\n\n"
        + bq(*card_lines)
        + "\n\n🔗 <b>Ссылка-подписка:</b>\n"
        f"<code>{subscription_url}</code>\n\n"
        "Добавьте ссылку в Happ, Hiddify, V2RayTun или Streisand. "
        "QR-код — следующим сообщением."
        + note
        + f"\n\nПроблемы? {settings.support_contact}"
    )


async def _send_subscription_bundle(
    bot: Bot,
    telegram_id: int,
    subscription_url: str,
    expires_at: datetime,
    *,
    premium_region_title: str | None = None,
) -> None:
    qr_bytes = await generate_qr_png_bytes(subscription_url)
    await bot.send_message(
        chat_id=telegram_id,
        text=_subscription_access_text(
            subscription_url,
            expires_at,
            premium_region_title=premium_region_title,
        ),
    )
    await bot.send_photo(
        chat_id=telegram_id,
        photo=BufferedInputFile(qr_bytes, filename="subscription_qr.png"),
        caption="QR-код ссылки-подписки.",
        reply_markup=back_to_menu_keyboard(),
    )


async def _credit_topup_payment(
    *,
    bot: Bot,
    session: AsyncSession,
    repo: Repository,
    external_invoice_id: str,
    payment_user_id: int,
    topup: ParsedTopupPayload,
) -> None:
    if topup.user_id != payment_user_id:
        logger.error(
            "Top-up payment user mismatch external_invoice_id=%s payload_user_id=%s payment_user_id=%s",
            external_invoice_id,
            topup.user_id,
            payment_user_id,
        )
        return

    claimed = await repo.claim_pending_cryptobot_payment(external_invoice_id)
    if claimed is None:
        return

    try:
        entry = await wallet.deposit(
            session,
            topup.user_id,
            topup.amount_kopecks,
            kind=wallet.KIND_DEPOSIT,
            reference=f"cryptobot:{external_invoice_id}",
            description="Пополнение баланса через CryptoBot",
        )
    except Exception:
        logger.exception(
            "Failed to credit top-up external_invoice_id=%s user_id=%s",
            external_invoice_id,
            topup.user_id,
        )
        try:
            await session.rollback()
            await repo.update_payment_status(claimed.id, "pending")
        except Exception:
            logger.exception(
                "Failed to release top-up payment for retry external_invoice_id=%s",
                external_invoice_id,
            )
        return

    await repo.complete_payment_by_external_id(external_invoice_id)

    user = await repo.get_user(topup.user_id)
    if user is None:
        return
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=(
                f"💰 Баланс пополнен на {format_rub(topup.amount_kopecks)}.\n"
                f"Текущий баланс: {format_rub(entry.balance_after_kopecks)}"
            ),
            reply_markup=back_to_menu_keyboard(),
        )
    except Exception:
        logger.exception(
            "Failed to notify user about top-up user_id=%s external_invoice_id=%s",
            topup.user_id,
            external_invoice_id,
        )


async def poll_cryptobot_payments(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    try:
        invoices = await get_invoices_by_status("paid", count=100)
    except Exception:
        logger.exception("CryptoBot polling failed")
        return

    for invoice in invoices:
        external_invoice_id = invoice.get("invoice_id")
        if external_invoice_id is None:
            logger.warning("Skipping paid CryptoBot invoice without invoice_id: %s", invoice)
            continue

        async with session_pool() as session:
            repo = Repository(session)
            payment = await repo.get_payment_by_external_id(str(external_invoice_id))
            if payment is None:
                continue
            if payment.status != "pending":
                continue

            payload = str(invoice.get("payload") or payment.invoice_payload or "")

            try:
                topup = parse_topup_payload(payload)
            except ValueError:
                logger.exception(
                    "Invalid top-up payload for external_invoice_id=%s payload=%s",
                    external_invoice_id,
                    payload,
                )
                continue
            if topup is not None:
                await _credit_topup_payment(
                    bot=bot,
                    session=session,
                    repo=repo,
                    external_invoice_id=str(external_invoice_id),
                    payment_user_id=payment.user_id,
                    topup=topup,
                )
                continue

            try:
                payload_details = parse_invoice_payload_details(payload)
                payload_user_id, plan = payload_details.user_id, payload_details.plan
            except ValueError:
                logger.exception(
                    "Invalid CryptoBot invoice payload for external_invoice_id=%s payload=%s",
                    external_invoice_id,
                    payload,
                )
                continue

            if payload_user_id != payment.user_id:
                logger.error(
                    "CryptoBot payment user mismatch external_invoice_id=%s payload_user_id=%s payment_user_id=%s",
                    external_invoice_id,
                    payload_user_id,
                    payment.user_id,
                )
                continue

            claimed_payment = await repo.claim_pending_cryptobot_payment(str(external_invoice_id))
            if claimed_payment is None:
                continue
            claimed_payment_id = claimed_payment.id
            claimed_user_id = claimed_payment.user_id

            try:
                user = await repo.get_user(claimed_user_id)
                if user is None:
                    raise RuntimeError(f"CryptoBot payment has no user user_id={claimed_user_id}")

                access_kind = "subscription"
                subscription_url = ""
                config_text = ""
                premium_region_title = None

                if _remnawave_configured():
                    subscription = await activate_panel_subscription(
                        session=session,
                        user_id=claimed_user_id,
                        plan=plan,
                    )
                    if not subscription.subscription_url:
                        raise RuntimeError("Panel subscription has no subscription_url")
                    subscription_url = to_gateway_subscription_url(subscription.subscription_url)
                    tariff = resolve_tariff(plan)
                    if tariff.tier == "premium":
                        region_option = (
                            resolve_premium_region(payload_details.region)
                            if payload_details.region is not None
                            else None
                        )
                        assigned_node = await assign_subscription_to_node(
                            session=session,
                            subscription_id=subscription.id,
                            tier="premium",
                            region=region_option.code if region_option else None,
                            provision_request=ProvisionNodeRequest(
                                region=region_option.code if region_option else None,
                                country_code=region_option.country_code if region_option else None,
                            ),
                        )
                        assigned_region = assigned_node.region
                        try:
                            premium_region_title = resolve_premium_region(assigned_region).title
                        except ValueError:
                            premium_region_title = assigned_region
                else:
                    access_kind = "wireguard"
                    subscription = await activate_subscription(
                        session=session,
                        user_id=claimed_user_id,
                        plan=plan,
                    )
                    _, config_text = await ensure_user_peer(session=session, user_id=claimed_user_id)
            except Exception:
                logger.exception(
                    "Failed to provision CryptoBot payment external_invoice_id=%s user_id=%s",
                    external_invoice_id,
                    claimed_user_id,
                )
                try:
                    await session.rollback()
                    await repo.update_payment_status(claimed_payment_id, "pending")
                except Exception:
                    logger.exception(
                        "Failed to release CryptoBot payment for retry external_invoice_id=%s user_id=%s",
                        external_invoice_id,
                        claimed_user_id,
                    )
                continue

            completed_payment = await repo.complete_payment_by_external_id(str(external_invoice_id))
            if completed_payment is None:
                logger.warning(
                    "Provisioned CryptoBot payment was not completed external_invoice_id=%s user_id=%s",
                    external_invoice_id,
                    claimed_user_id,
                )
                continue

            try:
                await reward_referrer_for_payment(
                    session,
                    paid_user_id=claimed_user_id,
                    plan_code=plan,
                    payment_reference=f"cryptobot:{external_invoice_id}",
                )
            except Exception:
                # Referral reward is best-effort; never block access delivery.
                logger.exception(
                    "Failed to credit referral reward external_invoice_id=%s user_id=%s",
                    external_invoice_id,
                    claimed_user_id,
                )

            try:
                if access_kind == "subscription":
                    await _send_subscription_bundle(
                        bot=bot,
                        telegram_id=user.telegram_id,
                        subscription_url=subscription_url,
                        expires_at=subscription.expires_at,
                        premium_region_title=premium_region_title,
                    )
                else:
                    await _send_access_bundle(
                        bot=bot,
                        telegram_id=user.telegram_id,
                        config_text=config_text,
                        expires_at=subscription.expires_at,
                    )
            except Exception:
                logger.exception(
                    "Failed to deliver CryptoBot access bundle external_invoice_id=%s user_id=%s",
                    external_invoice_id,
                    claimed_user_id,
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
    if settings.CRYPTOBOT_TOKEN.strip():
        scheduler.add_job(
            poll_cryptobot_payments,
            trigger="interval",
            seconds=settings.CRYPTOBOT_POLL_INTERVAL,
            args=[bot, session_pool],
            id="poll_cryptobot_payments",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
        )
    else:
        logger.warning("CRYPTOBOT_TOKEN is empty: payment polling disabled")
    if settings.autoscale_premium_regions_list:
        scheduler.add_job(
            autoscale_check,
            trigger="interval",
            seconds=settings.AUTOSCALE_CHECK_INTERVAL_SECONDS,
            args=[session_pool],
            id="autoscale_check",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
        )
    return scheduler
