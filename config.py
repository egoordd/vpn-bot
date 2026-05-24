from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    BOT_TOKEN: SecretStr
    PAYMENT_TOKEN: str = ""
    DATABASE_URL: str
    REDIS_URL: str

    WG_CONFIG_PATH: str = "/etc/wireguard/clients"
    WG_INTERFACE: str = "wg0"
    WG_SERVER_PUBLIC_KEY: str
    WG_SERVER_ENDPOINT: str
    WG_CLIENT_DNS: str = "1.1.1.1"
    WG_ALLOWED_IPS: str = "0.0.0.0/0, ::/0"
    WG_CLIENT_ADDRESS_POOL: str = "10.0.0.0/24"

    SUPPORT_USERNAME: str = "support"
    ADMIN_IDS: str = ""
    DB_ECHO: bool = False

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)

    @property
    def admin_ids_list(self) -> list[int]:
        if not self.ADMIN_IDS:
            return []
        raw = self.ADMIN_IDS.strip().strip("[]")
        return [int(item.strip()) for item in raw.split(",") if item.strip()]

    @property
    def bot_token(self) -> str:
        return self.BOT_TOKEN.get_secret_value()

    @property
    def support_contact(self) -> str:
        username = self.SUPPORT_USERNAME.strip()
        if not username:
            return "не указан"
        return username if username.startswith("@") else f"@{username}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
