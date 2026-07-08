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

    WG_CONFIG_PATH: str = "/etc/wireguard/clients"
    WG_INTERFACE: str = "awg0"
    WG_SERVER_PUBLIC_KEY: str
    WG_SERVER_ENDPOINT: str
    WG_CLIENT_DNS: str = "1.1.1.1"
    WG_ALLOWED_IPS: str = "0.0.0.0/0, ::/0"
    WG_CLIENT_ADDRESS_POOL: str = "10.0.0.0/24"
    AWG_JC: int = 4
    AWG_JMIN: int = 40
    AWG_JMAX: int = 70
    AWG_S1: int = 50
    AWG_S2: int = 100
    AWG_H1: int = 1234567
    AWG_H2: int = 2345678
    AWG_H3: int = 3456789
    AWG_H4: int = 4567890

    # AmneziaWG nodes for the multi-protocol subscription. Each user is given a
    # peer on every node here (provisioned over SSH). JSON: code -> {flag, name,
    # ssh_host, ssh_user, endpoint, server_pubkey, subnet}. Empty -> AWG disabled.
    AWG_NODES: str = "{}"
    # Path to the SSH private key used to provision AWG peers on the nodes.
    # Must be passphraseless so the bot (under launchd, no ssh-agent) can use it.
    AWG_SSH_KEY: str = ""

    CRYPTOBOT_TOKEN: str = ""
    CRYPTOBOT_API_URL: str = "https://pay.crypt.bot/api"
    CRYPTOBOT_POLL_INTERVAL: int = 30
    # Manual RUB/USDT rate used to price wallet top-up invoices.
    # TODO: replace with a rate feed before card payments launch.
    RUB_PER_USDT: str = "90"

    # YooKassa card payments (API + webhook). Charged in RUB.
    # SHOP_ID + SECRET_KEY come from the YooKassa merchant panel (Настройки → Ключи API).
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: SecretStr = SecretStr("")
    YOOKASSA_API_URL: str = "https://api.yookassa.ru/v3"
    # Where YooKassa returns the buyer after payment (a Telegram deep link to the bot).
    YOOKASSA_RETURN_URL: str = ""
    # 54-ФЗ receipts (самозанятый/НПД): when True, attach a receipt object so
    # YooKassa issues the чек. Needs a buyer contact — RECEIPT_EMAIL is the fallback.
    YOOKASSA_RECEIPT_ENABLED: bool = False
    YOOKASSA_RECEIPT_EMAIL: str = ""

    PANEL_PROVIDER: str = "remnawave"

    BILLING_API_TOKEN: SecretStr = SecretStr("")

    REMNAWAVE_API_URL: str = ""
    REMNAWAVE_API_TOKEN: SecretStr = SecretStr("")
    REMNAWAVE_USERNAME_PREFIX: str = "tg"
    REMNAWAVE_DEFAULT_TRAFFIC_RESET_STRATEGY: str = "NO_RESET"
    REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS: str = ""
    REMNAWAVE_NODE_CONFIG_PROFILE_UUID: str = ""
    REMNAWAVE_NODE_INBOUND_UUIDS: str = ""
    REMNAWAVE_NODE_PORT: int = 2222
    REMNAWAVE_HOST_PORT: int = 0
    REMNAWAVE_HOST_TAG: str = "AUTO"
    REMNAWAVE_NODE_COUNTRY_CODE: str = "XX"
    REMNAWAVE_NODE_TRAFFIC_TRACKING: bool = False

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
    # Per-region Marzban inbounds for static premium nodes (region -> inbounds
    # dict). Premium users for a configured region are created with that
    # region's inbound so their traffic routes through that node.
    # Example: {"ams": {"vless": ["VLESS Reality AMS"]}}
    MARZBAN_REGION_INBOUNDS: str = "{}"
    MARZBAN_DATA_LIMIT_RESET_STRATEGY: str = "no_reset"

    VULTR_API_URL: str = "https://api.vultr.com/v2"
    VULTR_API_TOKEN: SecretStr = SecretStr("")
    VULTR_DEFAULT_REGION: str = "ams"
    VULTR_DEFAULT_PLAN: str = "vc2-1c-1gb"
    VULTR_DEFAULT_OS_ID: int = 0
    VULTR_SSH_KEY_IDS: str = ""
    VULTR_NODE_CAPACITY: int = 50
    VULTR_NODE_LABEL_PREFIX: str = "unlock"
    AUTOSCALE_CHECK_INTERVAL_SECONDS: int = 300
    AUTOSCALE_PREMIUM_REGIONS: str = ""
    AUTOSCALE_PREMIUM_MIN_FREE_SLOTS: int = 1
    AUTOSCALE_PREMIUM_MIN_ACTIVE_NODES: int = 0
    AUTOSCALE_MAX_PROVISIONS_PER_REGION: int = 1
    AUTOSCALE_DECOMMISSION_EMPTY: bool = True

    SUPPORT_USERNAME: str = "support"
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
    def yookassa_secret_key(self) -> str:
        return self.YOOKASSA_SECRET_KEY.get_secret_value()

    @property
    def remnawave_api_token(self) -> str:
        return self.REMNAWAVE_API_TOKEN.get_secret_value()

    @property
    def remnawave_node_inbound_uuids_list(self) -> list[str]:
        return [item.strip() for item in self.REMNAWAVE_NODE_INBOUND_UUIDS.split(",") if item.strip()]

    @property
    def remnawave_default_internal_squad_uuids_list(self) -> list[str]:
        return [item.strip() for item in self.REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS.split(",") if item.strip()]

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

    @property
    def marzban_region_inbounds_dict(self) -> dict[str, dict[str, list[str]]]:
        raw = self._parse_json_object(self.MARZBAN_REGION_INBOUNDS, "MARZBAN_REGION_INBOUNDS")
        result: dict[str, dict[str, list[str]]] = {}
        for region, inbounds in raw.items():
            if not isinstance(inbounds, dict):
                continue
            result[str(region).lower()] = {
                str(proto): [str(tag) for tag in tags]
                for proto, tags in inbounds.items()
                if isinstance(tags, list)
            }
        return result

    @property
    def awg_nodes_dict(self) -> dict[str, dict[str, str]]:
        raw = self._parse_json_object(self.AWG_NODES, "AWG_NODES")
        result: dict[str, dict[str, str]] = {}
        for code, node in raw.items():
            if isinstance(node, dict):
                result[str(code)] = {str(k): str(v) for k, v in node.items()}
        return result

    def marzban_inbounds_for_region(self, region: str | None) -> dict[str, list[str]] | None:
        """Marzban inbounds for a static premium region, or None if not configured."""
        if not region:
            return None
        return self.marzban_region_inbounds_dict.get(region.lower())

    @staticmethod
    def _parse_json_object(raw: str, field: str) -> dict[str, Any]:
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must be a JSON object") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be a JSON object")
        return value

    @property
    def vultr_api_token(self) -> str:
        return self.VULTR_API_TOKEN.get_secret_value()

    @property
    def vultr_ssh_key_ids_list(self) -> list[str]:
        return [item.strip() for item in self.VULTR_SSH_KEY_IDS.split(",") if item.strip()]

    @property
    def autoscale_premium_regions_list(self) -> list[str]:
        return [item.strip().lower() for item in self.AUTOSCALE_PREMIUM_REGIONS.split(",") if item.strip()]

    @property
    def rub_per_usdt(self) -> "Decimal":
        from decimal import Decimal

        value = Decimal(self.RUB_PER_USDT)
        if value <= 0:
            raise ValueError("RUB_PER_USDT must be positive")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
