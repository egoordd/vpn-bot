"""Документы сервиса в боте (13.10.2026).

Платёжный провайдер требует, чтобы политика конфиденциальности, пользовательское
соглашение, тарифы и контакты поддержки были всегда доступны отдельными кнопками.
Сами документы лежат на сайте заказчика: MARAT_SITE_URL (https://…), страницы
/privacy/, /terms/, /tariffs/. Без адреса сайта кнопок документов нет — бот как раньше.
"""
from __future__ import annotations

import os

SITE_URL = os.environ.get("MARAT_SITE_URL", "").strip().rstrip("/")
SUPPORT_EMAIL = os.environ.get("MARAT_SUPPORT_EMAIL", "").strip()


def links() -> dict[str, str]:
    """{privacy, terms, refund, tariffs} → адреса страниц; пусто, если сайт не задан."""
    if not SITE_URL.startswith("https://"):
        return {}
    return {
        "privacy": f"{SITE_URL}/privacy/",
        "terms": f"{SITE_URL}/terms/",
        "refund": f"{SITE_URL}/terms/#refund",
        "tariffs": f"{SITE_URL}/tariffs/",
    }


def screen_text() -> str:
    email = f"\n📧 Почта: {SUPPORT_EMAIL}" if SUPPORT_EMAIL else ""
    return (
        "📄 <b>Документы</b>\n\n"
        "Условия сервиса всегда доступны по кнопкам ниже:\n"
        "<blockquote>🔒 Политика конфиденциальности\n"
        "📜 Пользовательское соглашение\n"
        "💳 Тарифы и условия оплаты</blockquote>\n\n"
        "💬 <b>Поддержка</b> — кнопка ниже: напишите вопрос, ответ придёт в этот чат, обычно в течение "
        "нескольких часов, не позднее 24 часов." + email
    )


def checkout_note() -> str:
    """Строка под суммой к оплате: чем оплачивает человек и на каких условиях."""
    found = links()
    if not found:
        return ""
    return (
        "\n\nОплата разовая, без автосписаний. Оплачивая, вы принимаете "
        f"<a href=\"{found['terms']}\">пользовательское соглашение</a>."
    )
