from decimal import Decimal

import pytest

from services.money import (
    KOPECKS_IN_RUB,
    format_rub,
    kopecks_to_rubles,
    percent_of,
    rubles_to_kopecks,
)


@pytest.mark.unit
def test_rubles_to_kopecks_accepts_int_str_decimal():
    assert rubles_to_kopecks(149) == 14900
    assert rubles_to_kopecks("1.99") == 199
    assert rubles_to_kopecks(Decimal("0.01")) == 1
    assert KOPECKS_IN_RUB == 100


@pytest.mark.unit
def test_rubles_to_kopecks_rounds_half_up():
    assert rubles_to_kopecks("1.005") == 101


@pytest.mark.unit
def test_kopecks_to_rubles_roundtrip():
    assert kopecks_to_rubles(14900) == Decimal("149.00")
    assert kopecks_to_rubles(199) == Decimal("1.99")


@pytest.mark.unit
def test_format_rub_drops_trailing_zeros_for_whole_amounts():
    assert format_rub(14900) == "149₽"
    assert format_rub(19950) == "199.5₽"
    assert format_rub(199) == "1.99₽"


@pytest.mark.unit
def test_percent_of_rounds_half_up():
    assert percent_of(14900, 20) == 2980
    assert percent_of(199, 20) == 40  # 39.8 -> 40
    assert percent_of(14900, 0) == 0


@pytest.mark.unit
def test_percent_of_rejects_negative_percent():
    with pytest.raises(ValueError):
        percent_of(100, -5)
