import json
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
    # Optional proxy for Telegram API access (e.g. socks5://127.0.0.1:1086)
    # for networks where api.telegram.org is throttled or blocked.
    BOT_PROXY: str = ""
    SLOW_UPDATE_THRESHOLD_SECONDS: float = Field(default=1.0, gt=0)
    DATABASE_URL: str
    REDIS_URL: str

    # How long a checkout may sit pending before we ask the provider what
    # really became of it. Long enough that a buyer still filling in card
    # details is never disturbed.
    STALE_PAYMENT_HOURS: int = 3
    # YooKassa card payments (API + webhook). Charged in RUB.
    # SHOP_ID + SECRET_KEY come from the YooKassa merchant panel (Настройки → Ключи API).
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: SecretStr = SecretStr("")
    YOOKASSA_API_URL: str = "https://api.yookassa.ru/v3"
    # Where YooKassa returns the buyer after payment (a Telegram deep link to the bot).
    YOOKASSA_RETURN_URL: str = ""
    # Public origin of the website (no trailing slash) — used as the return
    # target for site-initiated card payments (/pay/success).
    WEB_BASE_URL: str = ""
    # 54-ФЗ receipts (самозанятый/НПД): when True, attach a receipt object so
    # YooKassa issues the чек. Needs a buyer contact — RECEIPT_EMAIL is the fallback.
    YOOKASSA_RECEIPT_ENABLED: bool = False
    YOOKASSA_RECEIPT_EMAIL: str = ""
    # When True, don't ask the buyer for email in the bot and send the receipt
    # WITHOUT a customer — YooKassa collects the email on its own checkout page.
    # Requires the shop's fiscalization to be set to "ЮKassa запрашивает контакты".
    YOOKASSA_COLLECT_EMAIL_ON_PAGE: bool = False

    # «Мой налог» (lknpd.nalog.ru) — auto-issue self-employed receipts after each
    # paid order (YooKassa stopped forming НПД чеки on 2025-12-29). Login is the
    # ЛКФЛ inn + password. Empty = disabled (no auto receipt).
    MOYNALOG_INN: str = ""
    MOYNALOG_PASSWORD: SecretStr = SecretStr("")
    # Alternative to inn+password for PIN/phone users: a long-lived refresh token
    # (minted once via the SMS challenge, see scripts/moynalog_login.py) plus the
    # device id it was bound to. Preferred over password when set.
    MOYNALOG_REFRESH_TOKEN: SecretStr = SecretStr("")
    MOYNALOG_DEVICE_ID: str = ""
    MOYNALOG_API_URL: str = "https://lknpd.nalog.ru/api/v1"
    # lknpd.nalog.ru answers only to Russian IPs; the bot VPS is in the US, so
    # requests must go through an RU egress. HTTP proxy URL, e.g.
    # "http://user:pass@ru-host:3128". Empty = direct (works only from RU).
    MOYNALOG_PROXY: str = ""
    # Наименование услуги в чеке.
    MOYNALOG_SERVICE_NAME: str = "UnLockVPN — VPN-подписка"

    # Outgoing email (stdlib SMTP) — used to send чеки to buyers. Works with any
    # provider: Gmail app-password (smtp.gmail.com:465), Resend SMTP, etc.
    # Empty SMTP_HOST = disabled (receipts then go to Telegram only).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465  # 465 = implicit TLS, anything else = STARTTLS
    SMTP_USER: str = ""
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_FROM: str = ""  # e.g. "UnLock VPN <unlockvpnru@gmail.com>"

    BILLING_API_TOKEN: SecretStr = SecretStr("")

    # Multi-protocol subscription gateway (VLESS + Hysteria2 per location).
    # When set, the bot serves users this gateway URL instead of the raw Marzban
    # subscription. Empty -> users get the plain Marzban (VLESS-only) link.
    SUB_GATEWAY_URL: str = ""

    MARZBAN_API_URL: str = ""
    MARZBAN_ACCESS_TOKEN: SecretStr = SecretStr("")
    MARZBAN_USERNAME: str = ""
    MARZBAN_PASSWORD: SecretStr = SecretStr("")
    MARZBAN_USERNAME_PREFIX: str = "tg"
    MARZBAN_DEFAULT_PROXIES: str = "{}"
    MARZBAN_DEFAULT_INBOUNDS: str = "{}"
    # Fallback only: every tariff now states whether its allowance refills, and
    # the panel gateway passes that through per user. The default is monthly so
    # a stale .env cannot quietly sell a one-shot bucket, which is exactly how
    # the quota came to last for the whole life of a link.
    MARZBAN_DATA_LIMIT_RESET_STRATEGY: str = "month"

    SUPPORT_USERNAME: str = "support"
    # News channel. It is the one contact point no operator can filter: when a
    # domain gets blocked, the new address is posted there first. Empty hides
    # the button rather than showing a dead link.
    NEWS_CHANNEL_USERNAME: str = "UnlockAccess"
    ADMIN_IDS: str = ""
    # Reports bot: receives ops errors, complaints (relayed) and payment
    # notifications; admin replies here are relayed back to users. Empty -> off.
    ALERTS_BOT_TOKEN: str = ""
    ALERTS_CHAT_ID: str = ""
    # Support bot: users open tickets here; the support relay forwards them to the
    # reports bot and routes the admin's replies back. Username = for the deep link.
    SUPPORT_BOT_TOKEN: str = ""
    SUPPORT_BOT_USERNAME: str = ""
    # Tribute card payments. API key verifies the webhook HMAC signature.
    # PLAN_MAP: JSON {"<tribute product/subscription id>": "<our plan code>"}.
    # DEFAULT_PLAN: fallback plan if an id isn't in the map. Empty -> disabled.
    TRIBUTE_API_KEY: str = ""
    TRIBUTE_PLAN_MAP: str = "{}"
    TRIBUTE_DEFAULT_PLAN: str = ""
    # Map of our plan code -> Tribute Telegram payment link (t.me/tribute/app?startapp=...).
    # The bot shows a "pay by card" button that opens Tribute INSIDE Telegram, so the
    # buyer is Telegram-identified and the new_digital_product webhook can auto-deliver.
    TRIBUTE_PAY_LINKS: str = "{}"
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
    def alerts_chat_id(self) -> str:
        """Chat that receives alerts; falls back to the first admin id."""
        cid = self.ALERTS_CHAT_ID.strip()
        if cid:
            return cid
        ids = self.admin_ids_list
        return str(ids[0]) if ids else ""

    @property
    def bot_token(self) -> str:
        return self.BOT_TOKEN.get_secret_value()

    @property
    def support_contact(self) -> str:
        # Prefer the real support-relay bot (users write there → tickets reach the
        # reports bot → replies route back). Fall back to a manual @username.
        username = self.SUPPORT_BOT_USERNAME.strip() or self.SUPPORT_USERNAME.strip()
        if not username:
            return "не указан"
        return username if username.startswith("@") else f"@{username}"

    @property
    def news_channel_url(self) -> str:
        username = self.NEWS_CHANNEL_USERNAME.strip().lstrip("@")
        return f"https://t.me/{username}" if username else ""

    @property
    def yookassa_secret_key(self) -> str:
        return self.YOOKASSA_SECRET_KEY.get_secret_value()

    @property
    def moynalog_password(self) -> str:
        return self.MOYNALOG_PASSWORD.get_secret_value()

    @property
    def moynalog_refresh_token(self) -> str:
        return self.MOYNALOG_REFRESH_TOKEN.get_secret_value()

    @property
    def smtp_password(self) -> str:
        return self.SMTP_PASSWORD.get_secret_value()

    @property
    def marzban_access_token(self) -> str:
        return self.MARZBAN_ACCESS_TOKEN.get_secret_value()

    @property
    def marzban_password(self) -> str:
        return self.MARZBAN_PASSWORD.get_secret_value()

    @property
    def marzban_default_proxies_dict(self) -> dict[str, Any]:
        return self._parse_json_object(self.MARZBAN_DEFAULT_PROXIES, "MARZBAN_DEFAULT_PROXIES")

    @property
    def marzban_default_inbounds_dict(self) -> dict[str, list[str]]:
        raw = self._parse_json_object(self.MARZBAN_DEFAULT_INBOUNDS, "MARZBAN_DEFAULT_INBOUNDS")
        return {str(key): [str(item) for item in value] for key, value in raw.items() if isinstance(value, list)}

    @property
    def tribute_plan_map_dict(self) -> dict[str, str]:
        raw = self._parse_json_object(self.TRIBUTE_PLAN_MAP, "TRIBUTE_PLAN_MAP")
        return {str(key): str(value) for key, value in raw.items()}

    @property
    def tribute_pay_links_dict(self) -> dict[str, str]:
        raw = self._parse_json_object(self.TRIBUTE_PAY_LINKS, "TRIBUTE_PAY_LINKS")
        return {str(key): str(value) for key, value in raw.items()}

    @staticmethod
    def _parse_json_object(raw: str, field: str) -> dict[str, Any]:
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must be a JSON object") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be a JSON object")
        return value

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
