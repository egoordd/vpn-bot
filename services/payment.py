from __future__ import annotations

import uuid

from aiogram import Bot
from aiogram.types import LabeledPrice

from config import settings


PLANS: dict[str, dict[str, int | str]] = {
    "1m": {
        "title": "Базовый",
        "label": "1 месяц",
        "days": 30,
        "amount": 199,
        "description": "VPN-доступ на 30 дней",
    },
    "3m": {
        "title": "Стандарт",
        "label": "3 месяца",
        "days": 90,
        "amount": 499,
        "description": "VPN-доступ на 90 дней",
    },
    "6m": {
        "title": "Полугодовой",
        "label": "6 месяцев",
        "days": 180,
        "amount": 899,
        "description": "VPN-доступ на 180 дней",
    },
}


def create_invoice_payload(user_id: int, plan: str) -> str:
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")
    return f"vpn:{user_id}:{plan}:{uuid.uuid4().hex}"


def parse_invoice_payload(payload: str) -> tuple[int, str]:
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "vpn":
        raise ValueError("Invalid invoice payload")
    user_id = int(parts[1])
    plan = parts[2]
    if plan not in PLANS:
        raise ValueError("Unknown invoice plan")
    return user_id, plan


async def send_invoice(bot: Bot, chat_id: int, user_id: int, plan: str, payload: str | None = None) -> None:
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")

    plan_data = PLANS[plan]
    invoice_payload = payload or create_invoice_payload(user_id=user_id, plan=plan)
    amount = int(plan_data["amount"])
    label = str(plan_data["label"])
    title = f"VPN {label}"
    description = str(plan_data["description"])

    await bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=invoice_payload,
        provider_token=settings.PAYMENT_TOKEN or "",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=amount)],
    )
