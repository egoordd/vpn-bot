import pytest

from services.tariffs import BYTES_IN_GB, resolve_tariff


@pytest.mark.unit
def test_resolve_tariff_supports_legacy_aliases():
    tariff = resolve_tariff("1m")

    assert tariff.code == "standard_1m"
    assert tariff.traffic_limit_bytes == 150 * BYTES_IN_GB


@pytest.mark.unit
def test_resolve_tariff_rejects_unknown_code():
    with pytest.raises(ValueError):
        resolve_tariff("missing")




@pytest.mark.unit
def test_country_flag_converts_iso_codes():
    from services.tariffs import country_flag

    assert country_flag("NL") == "🇳🇱"
    assert country_flag("de") == "🇩🇪"
    assert country_flag("PL") == "🇵🇱"
    assert country_flag("") == "🌍"
    assert country_flag("XXX") == "🌍"


@pytest.mark.unit
def test_paid_tariffs_sell_a_monthly_allowance_not_a_term_pool():
    """A longer term buys more months of the same allowance, not one big bucket.

    A pooled bucket let a heavy first month strand the customer for the rest of
    the term. Longer commitments deliberately receive a larger monthly bucket.
    """
    assert resolve_tariff("standard_1m").traffic_limit_bytes == 150 * BYTES_IN_GB
    for code in ("standard_3m", "standard_6m", "standard_12m"):
        assert resolve_tariff(code).traffic_limit_bytes == 200 * BYTES_IN_GB


@pytest.mark.unit
def test_every_paid_tariff_allows_five_devices():
    """Решение владельца 02.10.2026: на обычной подписке любого срока — до 5
    устройств (01.10 было «от 6 месяцев — 5, короче — 3»). Пробник остаётся на двух."""
    for code in ("standard_1m", "standard_3m", "standard_6m", "standard_12m"):
        assert resolve_tariff(code).device_limit == 5
    assert resolve_tariff("trial").device_limit == 2


@pytest.mark.unit
def test_long_term_allowance_total_uses_the_larger_monthly_bucket():
    assert resolve_tariff("standard_3m").total_traffic_gb == 600
    assert resolve_tariff("standard_6m").total_traffic_gb == 1200
    assert resolve_tariff("standard_12m").total_traffic_gb == 2400


@pytest.mark.unit
def test_trial_allowance_never_refills():
    """Three days never reach a refill boundary, and a refilling trial is free VPN."""
    trial = resolve_tariff("trial")

    assert trial.traffic_resets_monthly is False
    assert trial.traffic_months == 1
    assert trial.total_traffic_gb == 10


@pytest.mark.unit
def test_trial_runs_three_days():
    # 22.09.2026 вернули 3 дня: за неделю пробника платили реже (13% против 22%),
    # а покупали всё равно в последние дни.
    assert resolve_tariff("trial").duration_days == 3


@pytest.mark.unit
def test_day_counts_are_declined_for_russian():
    """Copy derives the trial length, so the wording has to survive any number.

    The length was hand-typed in thirteen places before; moving it from three
    days to seven meant editing all of them.
    """
    from bot.texts import plural_days, trial_days

    assert [plural_days(n) for n in (1, 2, 4, 5, 11, 14, 21, 22)] == [
        "1 день", "2 дня", "4 дня", "5 дней", "11 дней", "14 дней", "21 день", "22 дня",
    ]
    assert trial_days() == "3 дня"


def test_the_trial_covers_a_phone_and_a_computer():
    """Пробуют сервис сразу на двух устройствах; лимит в одно устройство читается
    как «не работает» и стоит нам покупки (случай из поддержки 11.09)."""
    assert resolve_tariff("trial").device_limit == 2
