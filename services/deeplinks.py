from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppImportGuide:
    code: str
    title: str
    deeplink: str | None
    steps: tuple[str, ...]


def build_app_import_guides(subscription_url: str) -> dict[str, AppImportGuide]:
    return {
        "hiddify": AppImportGuide(
            code="hiddify",
            title="Hiddify",
            deeplink=f"hiddify://import/{subscription_url}#UnLock",
            steps=(
                "Откройте Hiddify.",
                "Нажмите + и выберите Import from Clipboard или вставьте ссылку вручную.",
                "Если deeplink сработал, профиль появится автоматически.",
            ),
        ),
        "v2raytun": AppImportGuide(
            code="v2raytun",
            title="V2RayTun",
            deeplink=f"v2raytun://import/{subscription_url}",
            steps=(
                "Откройте V2RayTun.",
                "Нажмите + и выберите импорт по URL или QR.",
                "Вставьте ссылку-подписку и обновите профиль.",
            ),
        ),
        "streisand": AppImportGuide(
            code="streisand",
            title="Streisand",
            deeplink=None,
            steps=(
                "Откройте Streisand.",
                "Выберите импорт подписки по URL или QR.",
                "Вставьте ссылку-подписку из сообщения бота.",
            ),
        ),
        "singbox": AppImportGuide(
            code="singbox",
            title="sing-box",
            deeplink=None,
            steps=(
                "Откройте sing-box.",
                "Создайте remote profile.",
                "Вставьте ссылку-подписку как URL профиля.",
            ),
        ),
    }
