"""Шлюз подписок собственной установки Etalon (deploy/etalon-stack): Happ — JSON с Авто-выбором,
остальные клиенты — список ссылок, истёкшая подписка — пусто, чужие пути — 404."""

import base64
import importlib.util
import json
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

STACK = Path(__file__).resolve().parents[1] / "deploy" / "etalon-stack"
LINK = (
    "vless://11111111-2222-3333-4444-555555555555@89.221.203.114:{port}?security=reality&type=tcp"
    "&flow=xtls-rprx-vision&sni=89.221.203.114.sslip.io&fp=firefox&pbk=xKVY0REl4TrK06IaiEax38V4cueiOwFtFUAjhMfnVVU"
    "&sid=0123456789abcdef#{name}"
)
LINKS = [LINK.format(port=443, name="%F0%9F%87%B3%F0%9F%87%B1%20%D0%9D%D0%B8%D0%B4%D0%B5%D1%80%D0%BB%D0%B0%D0%BD%D0%B4%D1%8B"),
         LINK.format(port=2053, name="%F0%9F%87%A9%F0%9F%87%AA%20%D0%93%D0%B5%D1%80%D0%BC%D0%B0%D0%BD%D0%B8%D1%8F")]


@pytest.fixture()
def gw(monkeypatch):
    monkeypatch.syspath_prepend(str(STACK))
    sys.modules.pop("etalon_gateway", None)
    spec = importlib.util.spec_from_file_location("etalon_gateway", STACK / "etalon_gateway.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upstream(gw, monkeypatch, expire):
    def fake_fetch(token):
        if token != "tok12345678":
            return None
        return list(LINKS), f"upload=0; download=0; total=0; expire={expire}"
    monkeypatch.setattr(gw, "fetch_upstream", fake_fetch)


def test_happ_gets_auto_choice_ru_mode_and_each_country(gw, monkeypatch):
    _upstream(gw, monkeypatch, int(time.time()) + 3600)
    status, headers, body = gw.render("/sub/tok12345678", "Happ/3.7.0")
    configs = json.loads(body)
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert [c["remarks"] for c in configs][:2] == ["⚡️ Авто-выбор", "🇷🇺 Режим РУ-сервисов"]
    assert len(configs) == 4, "авто, РУ-режим и по пункту на страну"
    assert base64.b64decode(headers["profile-title"].split(":", 1)[1]).decode() == "Etalon VPN"
    assert "expire=" in headers["subscription-userinfo"]


def test_other_clients_get_plain_links(gw, monkeypatch):
    _upstream(gw, monkeypatch, 0)
    status, headers, body = gw.render("/sub/tok12345678", "v2rayNG/1.9")
    assert status == 200 and base64.b64decode(body).decode().splitlines() == LINKS


def test_expired_subscription_is_empty(gw, monkeypatch):
    _upstream(gw, monkeypatch, int(time.time()) - 60)
    status, _, body = gw.render("/sub/tok12345678", "Happ/3.7.0")
    assert status == 200 and base64.b64decode(body) == b""


def test_unknown_token_and_foreign_paths_are_404(gw, monkeypatch):
    _upstream(gw, monkeypatch, 0)
    assert gw.render("/sub/missing0000", "Happ/3.7.0")[0] == 404
    assert gw.render("/api/admin", "Happ/3.7.0")[0] == 404
    assert gw.render("/sub/../../etc/passwd", "Happ/3.7.0")[0] == 404


def _limited_upstream(gw, monkeypatch, total):
    def fake_fetch(token):
        return list(LINKS), f"upload=0; download=0; total={total}; expire={int(time.time()) + 3600}"
    monkeypatch.setattr(gw, "fetch_upstream", fake_fetch)


# Токен Marzban: base64url("имя,время") без «=» и 10 символов подписи.
TOKEN = base64.urlsafe_b64encode(b"corp_mrt_42,1792074617").decode().rstrip("=") + "AbCdEfGhIj"


def test_trial_allows_two_devices_then_shows_the_limit_entry(gw, monkeypatch, tmp_path):
    monkeypatch.setattr(gw, "DEVICE_DB", str(tmp_path / "devices.sqlite3"))
    _limited_upstream(gw, monkeypatch, total=10 * 1024**3)
    path = f"/sub/{TOKEN}"
    for hwid in ("phone", "laptop", "phone"):
        status, _, body = gw.render(path, "Happ/3.7.0", {"x-hwid": hwid, "x-device-model": "iPhone"})
        assert status == 200 and json.loads(body)[0]["remarks"] == "⚡️ Авто-выбор", hwid
    status, _, body = gw.render(path, "Happ/3.7.0", {"x-hwid": "tablet"})
    assert "Лимит устройств" in urllib.parse.unquote(base64.b64decode(body).decode())
    assert gw.render(path, "Happ/3.7.0", {})[0] == 200, "без x-hwid не блокируем"
    assert sorted(gw.devices("corp_mrt_42")) == ["laptop", "phone"]


def test_paid_subscription_allows_five_devices(gw, monkeypatch, tmp_path):
    monkeypatch.setattr(gw, "DEVICE_DB", str(tmp_path / "devices.sqlite3"))
    _limited_upstream(gw, monkeypatch, total=0)
    for n in range(5):
        _, _, body = gw.render(f"/sub/{TOKEN}", "Happ/3.7.0", {"x-hwid": f"dev{n}"})
        assert json.loads(body)[0]["remarks"] == "⚡️ Авто-выбор"
    _, _, body = gw.render(f"/sub/{TOKEN}", "Happ/3.7.0", {"x-hwid": "dev5"})
    assert "Лимит устройств" in urllib.parse.unquote(base64.b64decode(body).decode())


def test_token_username(gw):
    assert gw.token_username(TOKEN) == "corp_mrt_42"
    assert gw.token_username("garbage!!") is None


def test_cli_lists_and_forgets_devices(gw, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gw, "DEVICE_DB", str(tmp_path / "devices.sqlite3"))
    gw.device_allowed("corp_mrt_7", "iphone-1", 5, "iPhone 15", "iOS 18")
    gw.device_allowed("corp_mrt_7", "mac-1", 5)
    assert gw.cli(["devices", "corp_mrt_7"]) == 0
    assert "iPhone 15" in capsys.readouterr().out
    assert gw.cli(["forget", "corp_mrt_7", "mac-1"]) == 0
    assert gw.devices("corp_mrt_7") == ["iphone-1"]
    assert gw.cli(["forget", "corp_mrt_7"]) == 0
    assert gw.devices("corp_mrt_7") == []
    assert gw.cli(["oops"]) == 2
