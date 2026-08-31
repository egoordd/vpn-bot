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
    the term, and the bot has always advertised "150 ГБ трафика в месяц".
    """
    for code in ("standard_1m", "standard_3m", "standard_6m", "standard_12m"):
        assert resolve_tariff(code).traffic_limit_bytes == 150 * BYTES_IN_GB


@pytest.mark.unit
def test_monthly_allowance_still_adds_up_to_the_old_term_total():
    """Pacing the quota must not quietly shrink what the term is worth."""
    assert resolve_tariff("standard_3m").total_traffic_gb == 450
    assert resolve_tariff("standard_6m").total_traffic_gb == 900
    assert resolve_tariff("standard_12m").total_traffic_gb == 1800


@pytest.mark.unit
def test_trial_allowance_never_refills():
    """Three days never reach a refill boundary, and a refilling trial is free VPN."""
    trial = resolve_tariff("trial")

    assert trial.traffic_resets_monthly is False
    assert trial.traffic_months == 1
    assert trial.total_traffic_gb == 10


@pytest.mark.unit
def test_trial_runs_a_week():
    assert resolve_tariff("trial").duration_days == 7


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
    assert trial_days() == "7 дней"
