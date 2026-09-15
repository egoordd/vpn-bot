"""Картинки над экранами зеркала.

Каждая картинка уходит в Telegram один раз: дальше отправляется её file_id, и
человек на слабом канале получает экран без повторной загрузки трёхсот килобайт.

Любая осечка — файла нет, Telegram не принял, подпись длиннее разрешённого —
молча превращает экран в обычный текстовый. Баннер не повод не показать меню.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Путь задаётся переменной окружения, потому что служба зеркала может быть
# запущена не из корня проекта, а без картинок экран должен остаться рабочим.
BANNERS_DIR = Path(os.environ.get("MIRROR_BANNERS_DIR", "assets/mirror"))
WELCOME = BANNERS_DIR / "banner_welcome.png"
CABINET = BANNERS_DIR / "banner_cabinet.png"
EXPIRED = BANNERS_DIR / "banner_expired.png"

# Telegram обрезает подпись под фото на 1024 символах — длинный экран остаётся текстом.
CAPTION_LIMIT = 1024

_file_ids: dict[str, str] = {}


class PhotoSender(Protocol):
    async def call(self, method: str, payload: Mapping[str, Any] | None = None) -> Any: ...

    async def upload_photo(self, payload: Mapping[str, Any], path: Path) -> Any: ...


def _callbacks(keyboard: Mapping[str, Any]) -> set[str]:
    return {
        button["callback_data"]
        for row in keyboard.get("inline_keyboard", [])
        for button in row
        if "callback_data" in button
    }


def pick(keyboard: Mapping[str, Any]) -> Path:
    """Картинка по тому, что экран предлагает сделать.

    Состояние подписки уже прочитано при сборке меню, и повторный поход в базу
    ради картинки был бы лишним: кнопки говорят то же самое. Подключение
    устройства предлагают только тому, у кого подписка работает; пробный период —
    только новичку; остальным остаются тарифы, а это человек, у которого доступ
    закончился.
    """

    callbacks = _callbacks(keyboard)
    if "connect_device" in callbacks:
        return CABINET
    if "activate_trial" in callbacks:
        return WELCOME
    return EXPIRED


async def send(
    api: PhotoSender,
    chat_id: int,
    banner: Path,
    caption: str,
    keyboard: Mapping[str, Any],
) -> bool:
    """Отправить экран картинкой. False — не вышло, нужно показать текстом."""

    if len(caption) > CAPTION_LIMIT:
        return False
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": dict(keyboard),
    }
    cached = _file_ids.get(str(banner))
    try:
        if cached:
            await api.call("sendPhoto", {**payload, "photo": cached})
            return True
        result = await api.upload_photo(payload, banner)
    except Exception:  # noqa: BLE001 — см. docstring модуля: экран важнее картинки
        # Устаревший file_id — тоже осечка: в следующий раз загрузим заново.
        _file_ids.pop(str(banner), None)
        logger.warning("Баннер %s не отправился, показываю экран текстом", banner, exc_info=True)
        return False

    sizes = (result or {}).get("photo") or []
    if sizes and sizes[-1].get("file_id"):
        _file_ids[str(banner)] = sizes[-1]["file_id"]
    return True
