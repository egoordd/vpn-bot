from __future__ import annotations

from dataclasses import dataclass


BYTES_IN_GB = 1024**3


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

    @property
    def traffic_limit_bytes(self) -> int | None:
        if self.traffic_gb is None:
            return None
        return self.traffic_gb * BYTES_IN_GB


@dataclass(frozen=True)
class RegionOption:
    code: str
    title: str
    city: str
    country_code: str
    is_on_demand: bool = False


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
        description="Пробный доступ на 10 ГБ",
        sort_order=0,
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
        description="Общий тариф на 30 дней",
        sort_order=10,
    ),
    "standard_3m": Tariff(
        code="standard_3m",
        title="Standard 3 месяца",
        tier="standard",
        duration_days=90,
        price_rub=399,
        crypto_amount="4.99",
        traffic_gb=450,
        device_limit=3,
        description="Общий тариф на 90 дней",
        sort_order=20,
    ),
    "standard_6m": Tariff(
        code="standard_6m",
        title="Standard 6 месяцев",
        tier="standard",
        duration_days=180,
        price_rub=699,
        crypto_amount="7.99",
        traffic_gb=900,
        device_limit=5,
        description="Общий тариф на 180 дней",
        sort_order=30,
    ),
    "standard_12m": Tariff(
        code="standard_12m",
        title="Standard 12 месяцев",
        tier="standard",
        duration_days=365,
        price_rub=1199,
        crypto_amount="12.99",
        traffic_gb=1800,
        device_limit=5,
        description="Общий тариф на 12 месяцев",
        sort_order=40,
    ),
    "premium_1m": Tariff(
        code="premium_1m",
        title="Premium 1 месяц",
        tier="premium",
        duration_days=30,
        price_rub=399,
        crypto_amount="4.99",
        traffic_gb=300,
        device_limit=5,
        description="Premium-тариф на 30 дней",
        sort_order=50,
    ),
    "premium_3m": Tariff(
        code="premium_3m",
        title="Premium 3 месяца",
        tier="premium",
        duration_days=90,
        price_rub=999,
        crypto_amount="11.99",
        traffic_gb=900,
        device_limit=5,
        description="Premium-тариф на 90 дней",
        sort_order=60,
    ),
    "premium_6m": Tariff(
        code="premium_6m",
        title="Premium 6 месяцев",
        tier="premium",
        duration_days=180,
        price_rub=1799,
        crypto_amount="19.99",
        traffic_gb=1800,
        device_limit=8,
        description="Premium-тариф на 180 дней",
        sort_order=70,
    ),
    "premium_12m": Tariff(
        code="premium_12m",
        title="Premium 12 месяцев",
        tier="premium",
        duration_days=365,
        price_rub=2999,
        crypto_amount="34.99",
        traffic_gb=3600,
        device_limit=8,
        description="Premium-тариф на 12 месяцев",
        sort_order=80,
    ),
}


PREMIUM_REGIONS: dict[str, RegionOption] = {
    "ams": RegionOption(
        code="ams",
        title="Нидерланды, Амстердам",
        city="Amsterdam",
        country_code="NL",
    ),
    "fra": RegionOption(
        code="fra",
        title="Германия, Франкфурт",
        city="Frankfurt",
        country_code="DE",
    ),
    "waw": RegionOption(
        code="waw",
        title="Польша, Варшава",
        city="Warsaw",
        country_code="PL",
        is_on_demand=True,
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


def resolve_premium_region(code: str) -> RegionOption:
    region_code = code.strip().lower()
    try:
        return PREMIUM_REGIONS[region_code]
    except KeyError as exc:
        raise ValueError(f"Unknown premium region: {code}") from exc
