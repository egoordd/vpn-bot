"""Несколько подписок на одном аккаунте.

Каждая подписка — отдельный пользователь в панели со своей ссылкой и своими
устройствами. Основная живёт под обычным именем (``tg_<id>``), дополнительные —
под тем же именем с номером: ``tg_<id>_s2``, ``tg_<id>_s3``… Номер по имени и
отличает их: все подписки, выданные до появления дополнительных, — основные.

Покупка несёт цель:
- ``None`` — продлить основную (как было всегда);
- ``"new"`` — завести ещё одну;
- ``"<id>"`` — продлить подписку с этим номером строки в базе.
"""

from __future__ import annotations

import re

from database.models import Subscription

MAX_SUBSCRIPTIONS = 5
TARGET_NEW = "new"

_SLOT_RE = re.compile(r"_s(\d+)$")
_TARGET_RE = re.compile(r"^(new|\d{1,12})$")


def slot_number(panel_username: str | None) -> int:
    """1 — основная подписка, 2… — дополнительные."""
    match = _SLOT_RE.search(panel_username or "")
    return int(match.group(1)) if match else 1


def is_extra(panel_username: str | None) -> bool:
    return slot_number(panel_username) > 1


def slot_username(base_username: str, number: int) -> str:
    return base_username if number <= 1 else f"{base_username}_s{number}"


def free_slot_number(active: list[Subscription]) -> int:
    """Наименьший свободный номер дополнительной подписки среди действующих."""
    taken = {slot_number(row.panel_username) for row in active}
    number = 2
    while number in taken:
        number += 1
    return number


def active_slot_count(active: list[Subscription]) -> int:
    return len({slot_number(row.panel_username) for row in active})


def can_add(active: list[Subscription]) -> bool:
    return bool(active) and active_slot_count(active) < MAX_SUBSCRIPTIONS


def label(subscription: Subscription) -> str:
    number = slot_number(subscription.panel_username)
    return "Подписка 1 · основная" if number == 1 else f"Подписка {number}"


def is_valid_target(target: str | None) -> bool:
    return target is None or bool(_TARGET_RE.match(target))


def split_plan_target(raw: str) -> tuple[str, str | None]:
    """«standard_1m@new» → («standard_1m», «new»). Без «@» цели нет."""
    plan, sep, target = (raw or "").partition("@")
    if not sep:
        return plan, None
    if not is_valid_target(target):
        raise ValueError("Invalid purchase target")
    return plan, target


def with_target(plan: str, target: str | None) -> str:
    return f"{plan}@{target}" if target else plan
