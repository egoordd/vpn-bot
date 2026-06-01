import re

import pytest

from services.payment import PLANS, create_invoice_payload, parse_invoice_payload


@pytest.mark.unit
def test_plans_shape():
    assert set(PLANS) == {"1m", "3m", "6m"}
    for plan in PLANS.values():
        assert {"days", "rub_amount", "crypto_amount"} <= set(plan)


@pytest.mark.unit
def test_create_invoice_payload_format():
    payload = create_invoice_payload(42, "1m")
    assert re.match(r"^unlock:42:1m:[0-9a-f]{32}$", payload)


@pytest.mark.unit
def test_create_invoice_payload_unknown_plan():
    with pytest.raises(ValueError):
        create_invoice_payload(42, "bad")


@pytest.mark.unit
def test_parse_invoice_payload_round_trip():
    payload = create_invoice_payload(777, "3m")
    assert parse_invoice_payload(payload) == (777, "3m")


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        "wrong:1:1m:abc",
        "unlock:1:1m",
        "unlock:1:bad:abc",
        "unlock:not-int:1m:abc",
    ],
)
def test_parse_invoice_payload_invalid(payload):
    with pytest.raises(ValueError):
        parse_invoice_payload(payload)
