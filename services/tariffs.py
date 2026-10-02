from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone


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
    # Скрытый тариф не показывается ни в меню бота, ни на сайте и не продаётся
    # через сайт: его открывает только персональное предложение (services/winback.py).
    hidden: bool = False

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



_BASE_TARIFFS: dict[str, Tariff] = {
    "trial": Tariff(
        code="trial",
        title="Пробник",
        tier="trial",
        duration_days=3,
        price_rub=0,
        crypto_amount="0",
        traffic_gb=10,
        # Два устройства, а не одно: человек пробует сервис на телефоне и на
        # компьютере одновременно, и упереться в лимит на пробнике — это отказ
        # от покупки. Случай из поддержки 11.09: телефон работал, компьютер нет.
        device_limit=2,
        description="Пробный доступ: 3 дня, 10 ГБ",
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
        # Любой платный срок — до 5 устройств (решение владельца 02.10.2026;
        # 01.10 пять было только от 6 месяцев, короче — три).
        device_limit=5,
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
        traffic_gb=200,
        # Любой платный срок — до 5 устройств (решение владельца 02.10.2026).
        device_limit=5,
        description="Общий тариф на 90 дней, 200 ГБ в месяц",
        sort_order=20,
    ),
    "standard_6m": Tariff(
        code="standard_6m",
        title="Standard 6 месяцев",
        tier="standard",
        duration_days=180,
        price_rub=699,
        crypto_amount="7.99",
        traffic_gb=200,
        # От 6 месяцев — до 5 устройств (решение владельца 01.10.2026; 13.09 это
        # молча урезали до 3, и купившие полгода упёрлись в лимит).
        device_limit=5,
        description="Общий тариф на 180 дней, 200 ГБ в месяц",
        sort_order=30,
    ),
    "standard_12m": Tariff(
        code="standard_12m",
        title="Standard 12 месяцев",
        tier="standard",
        duration_days=365,
        price_rub=1199,
        crypto_amount="12.99",
        traffic_gb=200,
        # От 6 месяцев — до 5 устройств (решение владельца 01.10.2026; 13.09 это
        # молча урезали до 3, и купившие полгода упёрлись в лимит).
        device_limit=5,
        description="Общий тариф на 12 месяцев, 200 ГБ в месяц",
        sort_order=40,
    ),
    # Спецпредложение тем, кто взял пробник и так и не подключился (01.10.2026):
    # безлимит со скидкой ~10% от обычной цены (199/549/999). Только по личному
    # предложению из services/winback.py, поэтому hidden.
    "winback_unlim_1m": Tariff(
        code="winback_unlim_1m",
        title="Безлимит 30 дней",
        tier="standard",
        duration_days=30,
        price_rub=179,
        crypto_amount="2.29",
        traffic_gb=None,
        device_limit=3,
        description="Спецпредложение: 30 дней без лимита трафика",
        sort_order=110,
        hidden=True,
    ),
    "winback_unlim_3m": Tariff(
        code="winback_unlim_3m",
        title="Безлимит 3 месяца",
        tier="standard",
        duration_days=90,
        price_rub=489,
        crypto_amount="6.29",
        traffic_gb=None,
        device_limit=3,
        description="Спецпредложение: 90 дней без лимита трафика",
        sort_order=120,
        hidden=True,
    ),
    "winback_unlim_6m": Tariff(
        code="winback_unlim_6m",
        title="Безлимит 6 месяцев",
        tier="standard",
        duration_days=180,
        price_rub=899,
        crypto_amount="10.99",
        traffic_gb=None,
        device_limit=3,
        description="Спецпредложение: 180 дней без лимита трафика",
        sort_order=130,
        hidden=True,
    ),
}


# Повышение цен, объявленное рассылкой 23.09.2026: с 26.09.2026 00:00 по Москве.
# Переключается само — TARIFFS отдаёт цену на момент обращения, поэтому ни бот,
# ни зеркало, ни API перезапускать в полночь не нужно. Кто успел оплатить
# раньше, получает весь оплаченный срок по старой цене: сумма платежа
# фиксируется при его создании.
PRICE_RISE_AT = datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)  # 26.09 00:00 МСК
_RISEN_PRICES: dict[str, tuple[int, str]] = {
    "standard_1m": (199, "2.49"),
    "standard_3m": (549, "6.99"),
    "standard_6m": (999, "11.99"),
    "standard_12m": (1799, "19.99"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def price_rise_in_effect(now: datetime | None = None) -> bool:
    return (now or _now()) >= PRICE_RISE_AT


def _effective(tariff: Tariff, now: datetime | None = None) -> Tariff:
    risen = _RISEN_PRICES.get(tariff.code)
    if risen is None or not price_rise_in_effect(now):
        return tariff
    price_rub, crypto_amount = risen
    return replace(tariff, price_rub=price_rub, crypto_amount=crypto_amount)


class _ScheduledTariffs(Mapping[str, Tariff]):
    """Каталог тарифов с ценой, действующей прямо сейчас."""

    def __getitem__(self, code: str) -> Tariff:
        return _effective(_BASE_TARIFFS[code])

    def __iter__(self) -> Iterator[str]:
        return iter(_BASE_TARIFFS)

    def __len__(self) -> int:
        return len(_BASE_TARIFFS)


TARIFFS: Mapping[str, Tariff] = _ScheduledTariffs()




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
