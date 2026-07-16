import pytest

from services import xray_json

REALITY = (
    "vless://c66fa52c-2132-4857-bed4-965ec17a8895@144.172.101.217.sslip.io:443"
    "?security=reality&type=tcp&flow=xtls-rprx-vision&sni=144.172.101.217.sslip.io"
    "&fp=firefox&pbk=XfIF_PBK&sid=3684c6d0#%F0%9F%87%BA%F0%9F%87%B8%20%D0%A1%D0%A8%D0%90"
)
TROJAN = (
    "trojan://915b89bd@78.17.154.225.sslip.io:8444?security=tls&sni=78.17.154.225.sslip.io"
    "&type=tcp#%F0%9F%87%B5%F0%9F%87%B1%20Trojan"
)
HY2 = "hysteria2://pass@144.172.101.217.sslip.io:443?sni=x#US-Hy2"


@pytest.mark.unit
def test_build_outbound_vless_reality():
    out = xray_json.build_outbound(REALITY, "proxy-0")
    assert out["protocol"] == "vless"
    assert out["tag"] == "proxy-0"
    vnext = out["settings"]["vnext"][0]
    assert vnext["address"] == "144.172.101.217.sslip.io"
    assert vnext["port"] == 443
    assert vnext["users"][0]["id"] == "c66fa52c-2132-4857-bed4-965ec17a8895"
    assert vnext["users"][0]["flow"] == "xtls-rprx-vision"
    reality = out["streamSettings"]["realitySettings"]
    assert out["streamSettings"]["security"] == "reality"
    assert reality["publicKey"] == "XfIF_PBK"
    assert reality["shortId"] == "3684c6d0"
    assert reality["serverName"] == "144.172.101.217.sslip.io"
    assert reality["fingerprint"] == "firefox"


@pytest.mark.unit
def test_build_outbound_trojan_tls():
    out = xray_json.build_outbound(TROJAN, "proxy-1")
    assert out["protocol"] == "trojan"
    server = out["settings"]["servers"][0]
    assert server["address"] == "78.17.154.225.sslip.io"
    assert server["port"] == 8444
    assert server["password"] == "915b89bd"
    assert out["streamSettings"]["security"] == "tls"
    assert out["streamSettings"]["tlsSettings"]["serverName"] == "78.17.154.225.sslip.io"


@pytest.mark.unit
def test_build_outbound_skips_non_xray_and_garbage():
    assert xray_json.build_outbound(HY2, "proxy-0") is None
    assert xray_json.build_outbound("not-a-uri", "proxy-0") is None
    assert xray_json.build_outbound("vless://no-host-part", "proxy-0") is None


@pytest.mark.unit
def test_build_balancer_config_structure():
    cfg = xray_json.build_balancer_config([REALITY, HY2, TROJAN])
    assert cfg["remarks"] == "⚡️ Авто-обход"
    # hy2 excluded; two xray outbounds + direct + block
    tags = [o["tag"] for o in cfg["outbounds"]]
    assert tags == ["proxy-0", "proxy-1", "direct", "block"]
    balancer = cfg["routing"]["balancers"][0]
    assert balancer["selector"] == ["proxy-"]
    assert balancer["strategy"]["type"] == "leastPing"
    assert cfg["routing"]["rules"][0]["balancerTag"] == "auto"
    assert cfg["observatory"]["subjectSelector"] == ["proxy-"]
    # a socks + http inbound the client's TUN bridges to
    assert {i["protocol"] for i in cfg["inbounds"]} == {"socks", "http"}


@pytest.mark.unit
def test_build_balancer_config_none_without_xray_nodes():
    assert xray_json.build_balancer_config([HY2]) is None
    assert xray_json.build_balancer_config([]) is None


@pytest.mark.unit
def test_build_server_config_uses_uri_remark():
    cfg = xray_json.build_server_config(REALITY, 0)
    assert cfg["remarks"] == "🇺🇸 США"
    assert [o["tag"] for o in cfg["outbounds"]] == ["proxy", "direct", "block"]
    assert cfg["routing"]["rules"][0]["outboundTag"] == "proxy"


@pytest.mark.unit
def test_build_json_subscription_balancer_first_then_servers():
    configs = xray_json.build_json_subscription([REALITY, HY2, TROJAN])
    # balancer first; xray servers as JSON configs; hy2 passed through as a
    # raw URI string element in its original position
    assert len(configs) == 4
    assert configs[0]["remarks"] == "⚡️ Авто-обход"
    assert configs[1]["remarks"] == "🇺🇸 США"
    assert configs[2] == HY2
    assert configs[3]["remarks"] == "🇵🇱 Trojan"


@pytest.mark.unit
def test_build_json_subscription_empty_without_xray_nodes():
    assert xray_json.build_json_subscription([HY2]) == []
