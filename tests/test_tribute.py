import hashlib
import hmac

import pytest

from services import tribute


@pytest.mark.unit
def test_verify_signature_valid(monkeypatch):
    monkeypatch.setattr(tribute.settings, "TRIBUTE_API_KEY", "secret")
    body = b'{"name":"new_digital_product"}'
    sig = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert tribute.verify_signature(body, sig) is True


@pytest.mark.unit
def test_verify_signature_rejects_bad(monkeypatch):
    monkeypatch.setattr(tribute.settings, "TRIBUTE_API_KEY", "secret")
    assert tribute.verify_signature(b"{}", "deadbeef") is False


@pytest.mark.unit
def test_verify_signature_disabled_without_key(monkeypatch):
    monkeypatch.setattr(tribute.settings, "TRIBUTE_API_KEY", "")
    body = b"{}"
    sig = hmac.new(b"", body, hashlib.sha256).hexdigest()
    assert tribute.verify_signature(body, sig) is False


@pytest.mark.unit
def test_plan_for_maps_and_falls_back(monkeypatch):
    monkeypatch.setattr(tribute.settings, "TRIBUTE_PLAN_MAP", '{"123": "standard_1m"}')
    monkeypatch.setattr(tribute.settings, "TRIBUTE_DEFAULT_PLAN", "trial")
    assert tribute.plan_for(123) == "standard_1m"
    assert tribute.plan_for("123") == "standard_1m"
    assert tribute.plan_for(999) == "trial"

    monkeypatch.setattr(tribute.settings, "TRIBUTE_DEFAULT_PLAN", "")
    assert tribute.plan_for(999) is None
    assert tribute.plan_for(None) is None
