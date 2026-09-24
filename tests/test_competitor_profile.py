"""Тестовая копия автовыбора конкурента: только по /test, клиентам — прежнее."""

import json

import pytest

from services import competitor_profile, sub_gateway

REALITY = "vless://u@{host}:2087?security=reality&type=tcp&flow=xtls-rprx-vision&sni={host}.sslip.io&fp=firefox&pbk=K&sid=1#{host}"
HY2 = "hysteria2://pass@78.17.154.225:443?sni=78.17.154.225.sslip.io&insecure=0#PL%20Hy2"


def _links():
    return [
        REALITY.format(host="78.17.154.225"),
        HY2,
        REALITY.format(host="166.0.28.132"),
        REALITY.format(host="166.0.28.132").replace(":2087", ":2098"),
        REALITY.format(host="107.189.22.160"),
    ]


@pytest.mark.unit
def test_copy_matches_the_competitor_balancer():
    config = competitor_profile.build_test_config(_links())
    balancer = config["routing"]["balancers"][0]
    assert balancer["strategy"] == {
        "type": "leastLoad",
        "settings": {"baselines": ["1s"], "expected": 2, "maxRTT": "3s", "tolerance": 0.5},
    }
    assert balancer["fallbackTag"] == "direct"
    assert config["burstObservatory"]["pingConfig"] == {
        "connectivity": "", "destination": "http://www.gstatic.com/generate_204",
        "interval": "2m", "sampling": 3, "timeout": "1s",
    }
    assert config["dns"]["servers"][0]["address"] == "https://1.1.1.1/dns-query"


@pytest.mark.unit
def test_copy_routes_like_the_competitor():
    rules = competitor_profile.build_test_config(_links())["routing"]["rules"]
    assert rules[0] == {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"}
    assert rules[1]["protocol"] == ["bittorrent"] and rules[1]["outboundTag"] == "block"
    assert "domain:2ip.ru" in rules[2]["domain"] and rules[2]["balancerTag"] == "Balancer_R"
    assert rules[3]["outboundTag"] == "direct" and len(rules[3]["domain"]) == 71
    assert "geosite:category-ru" in rules[3]["domain"]
    assert rules[-1] == {"type": "field", "network": "tcp,udp", "balancerTag": "Balancer_R"}


@pytest.mark.unit
def test_copy_takes_one_server_per_address_and_the_first_hysteria():
    config = competitor_profile.build_test_config(_links())
    proxies = [o for o in config["outbounds"] if o["tag"].startswith("r")]
    assert [o["tag"] for o in proxies] == ["r", "r-2", "r-3", "r-4"]
    hy2 = next(o for o in proxies if o["protocol"] == "hysteria")
    assert hy2["streamSettings"]["finalmask"]["quicParams"]["keepAlivePeriod"] == 10
    assert hy2["streamSettings"]["tlsSettings"]["fingerprint"] == "chrome"


@pytest.mark.unit
def test_copy_is_none_without_servers():
    assert competitor_profile.build_test_config([]) is None


@pytest.mark.unit
def test_only_the_test_link_serves_the_copy(monkeypatch):
    monkeypatch.setattr(sub_gateway, "resolve_links", lambda token: (_links(), "expire=0"))

    body, userinfo, is_json = sub_gateway.build_test_json("tok")
    configs = json.loads(body)
    assert is_json and userinfo == "expire=0"
    assert [c["remarks"] for c in configs] == [competitor_profile.TEST_REMARKS]

    ordinary, _, _ = sub_gateway.build_auto_json("tok")
    first = json.loads(ordinary)[0]
    assert first["remarks"] == "⚡️ Авто-обход"
    assert first["routing"]["balancers"][0]["strategy"] == {"type": "leastPing"}
    assert not any(r.get("protocol") == ["bittorrent"] for r in first["routing"]["rules"])
