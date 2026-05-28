from __future__ import annotations

import uuid


PLANS: dict[str, dict[str, int | str]] = {
    "1m": {
        "title": "🚀 Старт",
        "label": "30 дней",
        "days": 30,
        "rub_amount": 149,
        "crypto_amount": "1.99",
        "description": "UnLock на 30 дней",
    },
    "3m": {
        "title": "💎 Стандарт",
        "label": "90 дней",
        "days": 90,
        "rub_amount": 399,
        "crypto_amount": "4.99",
        "description": "UnLock на 90 дней",
    },
    "6m": {
        "title": "👑 Полугодовой",
        "label": "180 дней",
        "days": 180,
        "rub_amount": 699,
        "crypto_amount": "7.99",
        "description": "UnLock на 180 дней",
    },
}


def create_invoice_payload(user_id: int, plan: str) -> str:
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")
    return f"unlock:{user_id}:{plan}:{uuid.uuid4().hex}"


def parse_invoice_payload(payload: str) -> tuple[int, str]:
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "unlock":
        raise ValueError("Invalid invoice payload")

    user_id = int(parts[1])
    plan = parts[2]
    if plan not in PLANS:
        raise ValueError("Unknown invoice plan")
    return user_id, plan
