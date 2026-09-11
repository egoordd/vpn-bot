"""Вход в российском облаке собирается из работающего московского моста.

Ошибка здесь стоит дорого: конфиг уезжает на сервер, который должен работать
именно тогда, когда у человека больше ничего не работает.
"""

import json

import pytest

from scripts.mobile_relay_config import TemplateError, build_config

TEMPLATE = {
    "dns": {"servers": ["77.88.8.8", "8.8.8.8"]},
    "routing": {"domainStrategy": "AsIs", "rules": []},
    "outbounds": [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
        {
            "tag": "pl",
            "protocol": "vless",
            "settings": {"vnext": [{"address": "78.17.154.225.sslip.io", "port": 2087,
                                    "users": [{"id": "pl-uuid", "flow": "xtls-rprx-vision"}]}]},
            "streamSettings": {"security": "reality", "sockopt": {"tcpKeepAliveIdle": 30}},
        },
        {
            "tag": "de",
            "protocol": "vless",
            "settings": {"vnext": [{"address": "166.0.28.132.sslip.io", "port": 2096,
                                    "users": [{"id": "de-uuid"}]}]},
            "streamSettings": {"security": "reality"},
        },
    ],
}

KEYS = {"uuid": "u-1", "private_key": "priv", "short_id": "abcd"}


def _config(**overrides):
    return build_config(TEMPLATE, **{**KEYS, **overrides})


def test_the_handshake_names_the_allowed_service_and_hands_probes_to_it():
    inbound = _config()["inbounds"][0]
    reality = inbound["streamSettings"]["realitySettings"]

    assert reality["serverNames"] == ["max.ru"]
    assert reality["dest"] == "max.ru:443", "проба должна уходить на настоящую службу"
    assert inbound["port"] == 443
    assert inbound["settings"]["clients"][0]["flow"] == "xtls-rprx-vision"


def test_our_own_names_never_appear_in_the_handshake():
    """Наш домен в SNI выдал бы вход: в белом списке его нет."""
    body = json.dumps(_config()["inbounds"], ensure_ascii=False)

    for ours in ("unlockru", "unlockproject", "sslip.io"):
        assert ours not in body


def test_exits_are_copied_with_their_credentials():
    outbounds = {o["tag"]: o for o in _config()["outbounds"]}

    assert set(outbounds) == {"direct", "block", "pl", "de"}
    assert outbounds["pl"]["settings"]["vnext"][0]["users"][0]["id"] == "pl-uuid"
    assert outbounds["de"] == TEMPLATE["outbounds"][3]


def test_a_dead_exit_does_not_take_the_whole_entry_down():
    """То, чего нет у московского моста: порт там жёстко привязан к стране."""
    routing = _config()["routing"]
    config = _config()

    assert routing["rules"][-1]["balancerTag"] == "exits"
    assert routing["balancers"][0]["selector"] == ["pl", "de"]
    assert config["observatory"]["subjectSelector"] == ["pl", "de"]


def test_russian_destinations_leave_from_the_russian_address():
    rules = _config()["routing"]["rules"]
    direct = [r for r in rules if r.get("outboundTag") == "direct"]

    assert ["geoip:ru"] in [r.get("ip") for r in direct]
    assert any("geosite:category-gov-ru" in (r.get("domain") or []) for r in direct)


def test_torrents_never_leave_the_russian_server():
    rules = _config()["routing"]["rules"]

    assert rules[0] == {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}


def test_the_carrier_cannot_time_the_tunnel_out():
    sockopt = _config()["inbounds"][0]["streamSettings"]["sockopt"]

    assert sockopt["tcpKeepAliveIdle"] == 30


def test_a_missing_exit_is_refused_rather_than_silently_dropped():
    with pytest.raises(TemplateError, match="us"):
        _config(exits=("pl", "us"))


def test_keys_are_required():
    with pytest.raises(ValueError):
        build_config(TEMPLATE, uuid="", private_key="p", short_id="s")
