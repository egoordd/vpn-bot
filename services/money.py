from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# Internal wallet balances and ledger amounts are stored as integer minor units
# of the rouble (kopecks). Product prices are quoted in whole roubles
# (`Tariff.price_rub`), so 1 RUB == 100 kopecks.
KOPECKS_IN_RUB = 100


def rubles_to_kopecks(rubles: int | str | Decimal) -> int:
    """Convert a rouble amount to integer kopecks (round half up)."""
    value = Decimal(str(rubles)) * KOPECKS_IN_RUB
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def kopecks_to_rubles(kopecks: int) -> Decimal:
    """Convert integer kopecks to a Decimal rouble amount."""
    return (Decimal(kopecks) / KOPECKS_IN_RUB).quantize(Decimal("0.01"))


def format_rub(kopecks: int) -> str:
    """Human-readable rouble string, dropping a trailing ``.00``."""
    amount = kopecks_to_rubles(kopecks)
    if amount == amount.to_integral_value():
        return f"{int(amount)}₽"
    return f"{amount.normalize()}₽"


def percent_of(amount_kopecks: int, percent: int) -> int:
    """Return ``percent`` percent of ``amount_kopecks`` (round half up)."""
    if percent < 0:
        raise ValueError("percent must be non-negative")
    value = Decimal(amount_kopecks) * Decimal(percent) / Decimal(100)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
