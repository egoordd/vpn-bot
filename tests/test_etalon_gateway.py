"""Шлюз подписок собственной установки Etalon (deploy/etalon-stack): Happ — JSON с Авто-выбором,
остальные клиенты — список ссылок, истёкшая подписка — пусто, чужие пути — 404."""

import base64
import importlib.util
import json
import sys
import time
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
