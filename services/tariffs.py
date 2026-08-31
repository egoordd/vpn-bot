from __future__ import annotations

from dataclasses import dataclass


BYTES_IN_GB = 1024**3


DAYS_IN_TRAFFIC_MONTH = 30


@dataclass(frozen=True)
class Tariff:
    code: str
    title: str
    tier: str
    duration_days: int
    price_rub: int
    crypto_amount: str
    traffic_gb: int | None
    device_limit: int | None
    description: str
    sort_order: int
    # Paid tariffs sell a monthly allowance that refills every 30 days, so
    # traffic_gb is the size of one month's bucket rather than the whole term.
    # The trial is a single 10 GB bucket that never refills — three days never
    # reach a refill boundary anyway, and a refilling trial would be free VPN.
    traffic_resets_monthly: bool = True

    @property
    def traffic_limit_bytes(self) -> int | None:
        """The quota the panel enforces at any one moment: one month's worth."""
        if self.traffic_gb is None:
            return None
        return self.traffic_gb * BYTES_IN_GB

    @property
    def traffic_months(self) -> int:
        """How many times the monthly bucket refills over the term."""
        if not self.traffic_resets_monthly:
            return 1
        return max(1, round(self.duration_days / DAYS_IN_TRAFFIC_MONTH))

    @property
    def total_traffic_gb(self) -> int | None:
        """Everything the tariff grants across the whole term, for copy."""
        if self.traffic_gb is None:
            return None
        return self.traffic_gb * self.traffic_months


def country_flag(country_code: str) -> str:
    """ISO-3166 alpha-2 country code -> flag emoji (regional indicators)."""
    code = (country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🌍"
    return "".join(chr(0x1F1E6 + (ord(ch) - ord("A"))) for ch in code)



TARIFFS: dict[str, Tariff] = {
    "trial": Tariff(
        code="trial",
        title="Пробник",
        tier="trial",
        duration_days=7,
        price_rub=0,
        crypto_amount="0",
        traffic_gb=10,
        device_limit=1,
        description="Пробный доступ: 7 дней, 10 ГБ",
        sort_order=0,
        traffic_resets_monthly=False,
    ),
    "standard_1m": Tariff(
        code="standard_1m",
        title="Standard 1 месяц",
        tier="standard",
        duration_days=30,
        price_rub=149,
        crypto_amount="1.99",
        traffic_gb=150,
        device_limit=3,
        description="Общий тариф на 30 дней, 150 ГБ в месяц",
        sort_order=10,
    ),
    "standard_3m": Tariff(
        code="standard_3m",
        title="Standard 3 месяца",
        tier="standard",
        duration_days=90,
        price_rub=399,
        crypto_amount="4.99",
        traffic_gb=150,
        device_limit=3,
        description="Общий тариф на 90 дней, 150 ГБ в месяц",
        sort_order=20,
    ),
    "standard_6m": Tariff(
        code="standard_6m",
        title="Standard 6 месяцев",
        tier="standard",
        duration_days=180,
        price_rub=699,
        crypto_amount="7.99",
        traffic_gb=150,
        device_limit=5,
        description="Общий тариф на 180 дней, 150 ГБ в месяц",
        sort_order=30,
    ),
    "standard_12m": Tariff(
        code="standard_12m",
        title="Standard 12 месяцев",
        tier="standard",
        duration_days=365,
        price_rub=1199,
        crypto_amount="12.99",
        traffic_gb=150,
        device_limit=5,
        description="Общий тариф на 12 месяцев, 150 ГБ в месяц",
        sort_order=40,
    ),
}




LEGACY_PLAN_ALIASES = {
    "1m": "standard_1m",
    "3m": "standard_3m",
    "6m": "standard_6m",
    "12m": "standard_12m",
}


def resolve_tariff(code: str) -> Tariff:
    tariff_code = LEGACY_PLAN_ALIASES.get(code, code)
    try:
        return TARIFFS[tariff_code]
    except KeyError as exc:
        raise ValueError(f"Unknown tariff: {code}") from exc


