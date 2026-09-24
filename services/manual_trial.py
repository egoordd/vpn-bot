"""Пробник, выданный вручную — для клиентов, которые пришли не через бота.

С 24.09.2026 много людей приходит с Авито: у них нет нашего бота, им нужна
просто ссылка. Администратор пишет /trial, получает ссылку и отправляет её
клиенту. Под ссылкой — отдельный аккаунт без Telegram, как у покупателей с
сайта (отрицательный telegram_id, чтобы бот никогда не пытался им написать), и
обычный пробник: те же 3 дня, 10 ГБ и 2 устройства, что в боте.

Источник пишется в users.source, поэтому в /funnel видно, сколько таких
пробников выдали и сколько из них дошло до оплаты. Захочет клиент продлить —
в боте есть /link: ссылка подписки доказывает, что аккаунт его.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from database.repository import Repository
from services.panel_gateway import PanelGateway
from services.subscription import activate_panel_subscription, to_gateway_subscription_url

DEFAULT_SOURCE = "avito"
_SOURCE_RE = re.compile(r"^[a-z0-9_]{1,32}$")


@dataclass(frozen=True)
class ManualTrial:
    telegram_id: int
    source: str
    subscription_url: str
    expires_at: datetime


def normalize_source(raw: str | None) -> str:
    """«Авито» и пустое → avito; иначе латиница, цифры и _ до 32 символов."""
    value = (raw or "").strip().lower()
    if not value or value in ("авито", "avito"):
        return DEFAULT_SOURCE
    if not _SOURCE_RE.match(value):
        raise ValueError("Источник: латиница, цифры и _, до 32 символов")
    return value


def _synthetic_telegram_id() -> int:
    # Тот же диапазон, что у аккаунтов с сайта: отрицательный и далеко от
    # зеркала (оно ниже -9·10¹⁵), чтобы доставка никогда не писала в Telegram.
    return -(secrets.randbits(52) + 1)


async def issue_manual_trial(
    session: AsyncSession,
    *,
    source: str = DEFAULT_SOURCE,
    panel_gateway: PanelGateway | None = None,
) -> ManualTrial:
    repo = Repository(session)
    telegram_id = _synthetic_telegram_id()
    user = await repo.create_user(telegram_id=telegram_id)
    user_id = user.id
    await repo.set_user_source_if_unset(user_id, source)
    subscription = await activate_panel_subscription(session, user_id, "trial", panel_gateway=panel_gateway)
    # Активация коммитит; в сессии со сбросом полей после коммита (так по
    # умолчанию в SQLAlchemy) ленивое чтение здесь падает, поэтому поля читаем
    # после явного обновления.
    await session.refresh(subscription)
    url = to_gateway_subscription_url(subscription.subscription_url)
    if not url:
        raise RuntimeError("Панель не вернула ссылку подписки")
    return ManualTrial(
        telegram_id=telegram_id,
        source=source,
        subscription_url=url,
        expires_at=subscription.expires_at,
    )


def client_message(trial: ManualTrial, expires_text: str) -> str:
    """Готовый текст для клиента — скопировать и отправить."""
    return (
        "Ваш пробный доступ UnLock VPN — 3 дня, 10 ГБ, до 2 устройств.\n\n"
        "1. Установите приложение Happ (App Store / Google Play).\n"
        "2. Скопируйте ссылку ниже и откройте Happ — он предложит добавить подписку.\n"
        "3. Нажмите большую кнопку подключения.\n\n"
        f"{trial.subscription_url}\n\n"
        f"Действует до {expires_text}.\n"
        "Продлить или купить — в боте @unlkvpn_bot, команда /link привяжет эту подписку."
    )
