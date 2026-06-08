import pytest

from services.tariffs import BYTES_IN_GB, PREMIUM_REGIONS, resolve_premium_region, resolve_tariff


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
def test_premium_tariffs_and_regions_are_available():
    tariff = resolve_tariff("premium_1m")

    assert tariff.tier == "premium"
    assert tariff.traffic_limit_bytes == 300 * BYTES_IN_GB
    assert set(PREMIUM_REGIONS) == {"ams", "fra", "waw"}
    assert resolve_premium_region("AMS").country_code == "NL"
