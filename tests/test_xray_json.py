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
    rules = cfg["routing"]["rules"]
    # Russian destinations bypass the tunnel (real IP → RU apps work, no detour)
    assert cfg["routing"]["domainStrategy"] == "IPOnDemand"
    assert rules[0]["ip"] == ["geoip:private"] and rules[0]["outboundTag"] == "direct"
    ru = next(r for r in rules if r.get("ip") == ["geoip:ru"])
    assert ru["outboundTag"] == "direct"
    # everything else load-balances across the foreign nodes
    assert rules[-1]["balancerTag"] == "auto"
    assert (cfg.get("burstObservatory") or cfg["observatory"])["subjectSelector"] == ["proxy-"]
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
    # RU-bypass rules first, then everything else through the picked server
    assert any(r.get("ip") == ["geoip:ru"] for r in cfg["routing"]["rules"])
    assert cfg["routing"]["rules"][-1]["outboundTag"] == "proxy"


@pytest.mark.unit
def test_build_json_subscription_balancer_first_then_servers():
    configs = xray_json.build_json_subscription([REALITY, HY2, TROJAN])
    # objects only: raw URI strings in the array break Happ's import, so hy2
    # is dropped from the JSON flavor (still present in the base64 one)
    assert [c["remarks"] for c in configs] == ["⚡️ Авто-обход", "🇺🇸 США", "🇵🇱 Trojan"]


@pytest.mark.unit
def test_build_json_subscription_empty_without_xray_nodes():
    assert xray_json.build_json_subscription([HY2]) == []


# --- «Авто-обход» failover behaviour ------------------------------------------

def _balancer(hosts=("h1", "h2")):
    uris = [
        f"vless://uuid@{h}:2096?security=reality&type=tcp&sni={h}&pbk=PBK&sid=SID#{h}"
        for h in hosts
    ]
    return xray_json.build_balancer_config(uris)


def _prober(config):
    """The health-probe block, whichever strategy built it."""
    return config.get("burstObservatory") or config["observatory"]


def _interval(config):
    b = config.get("burstObservatory")
    return b["pingConfig"]["interval"] if b else config["observatory"]["probeInterval"]


def test_probe_interval_is_short_enough_to_fail_over():
    """The probe interval IS the outage a user sits through when a node dies:
    the balancer cannot route around it until a fresh sample judges it."""
    interval = _interval(_balancer())
    assert interval.endswith("s"), f"expected seconds granularity, got {interval}"
    assert int(interval.rstrip("s")) <= 60, "failover would take over a minute"


def test_probe_url_is_plain_http():
    # https:// would add a TLS handshake to gstatic inside the tunnel on every
    # sample, inflating readings and skewing which node gets picked.
    prober = _prober(_balancer())
    url = prober.get("probeUrl") or prober["pingConfig"]["destination"]
    assert url.startswith("http://")


def test_default_strategy_ranks_on_latency(monkeypatch):
    """Latency ranking is what demotes a server that merely got slow — the
    "долго грузит" case — and it benchmarked faster than leastLoad on a real
    RU line, so it is the default."""
    config = _balancer()
    assert config["routing"]["balancers"][0]["strategy"] == {"type": "leastPing"}
    assert "observatory" in config and "burstObservatory" not in config


def test_leastload_alternative_pairs_with_burst_observatory(monkeypatch):
    # Opt-in alternative: ranks on stability rather than raw latency.
    monkeypatch.setattr(xray_json, "BALANCER_STRATEGY", "leastload")
    config = _balancer()
    strategy = config["routing"]["balancers"][0]["strategy"]
    assert strategy["type"] == "leastLoad"
    assert strategy["settings"]["maxRTT"].endswith("s")
    assert "burstObservatory" in config, "leastLoad requires burstObservatory"
    assert config["burstObservatory"]["pingConfig"]["sampling"] >= 2


def test_dns_has_a_fallback_resolver():
    servers = _balancer()["dns"]["servers"]
    assert len(servers) > 1, "keep a second resolver as fallback"


def test_balancer_covers_every_proxy_outbound():
    config = _balancer(("h1", "h2", "h3"))
    proxies = [o["tag"] for o in config["outbounds"] if o["tag"].startswith("proxy-")]
    assert len(proxies) == 3
    assert config["routing"]["balancers"][0]["selector"] == ["proxy-"]
    assert _prober(config)["subjectSelector"] == ["proxy-"]


# --- blocked platforms must never leak outside the tunnel ---------------------

def test_blocked_platforms_are_pinned_to_the_tunnel():
    """TikTok/Instagram run CDN edges inside RU. If a lookup lands on one, the
    geoip:ru rule would send the request straight out of the device to an edge
    that is frozen — which shows up as a stale feed, not an error."""
    rules = _balancer()["routing"]["rules"]
    pinned = next(r for r in rules if "domain" in r)
    geo_ru = next(i for i, r in enumerate(rules) if r.get("ip") == ["geoip:ru"])
    # decided by domain, before any IP rule can send it direct
    assert rules.index(pinned) < geo_ru
    assert pinned.get("balancerTag") == "auto"
    joined = " ".join(pinned["domain"])
    for host in ("tiktok.com", "instagram.com", "cdninstagram.com", "fbcdn.net",
                 "googlevideo.com", "youtube.com", "ibytedtos.com", "byteoversea.com"):
        assert f"domain:{host}" in joined


def test_single_server_config_pins_the_same_domains():
    config = xray_json.build_server_config(
        "vless://uuid@h1:2096?security=reality&sni=h1&pbk=P&sid=S#h1", 0
    )
    pinned = next(r for r in config["routing"]["rules"] if "domain" in r)
    assert pinned.get("outboundTag") == "proxy"


def test_dns_stays_remote_so_blocked_domains_resolve():
    """The RU ISP resolver answers nothing for blocked domains, so the device's
    own resolver cannot be trusted to look up TikTok/Instagram CDNs."""
    assert _balancer()["dns"]["servers"] == ["1.1.1.1", "8.8.8.8"]


# --- XHTTP transport ----------------------------------------------------------

XHTTP_URI = (
    "vless://uuid@78.17.154.225.sslip.io:2097?security=reality&type=xhttp"
    "&path=%2Fabc123&mode=auto&extra=%7B%22xPaddingBytes%22%3A+%22100-1000%22%7D"
    "&sni=78.17.154.225.sslip.io&fp=chrome&pbk=PBK&sid=SID#PL-XHTTP"
)


def test_xhttp_link_carries_its_transport_block():
    """Naming the network without its path yields a config that simply cannot
    connect — the path is where the tunnel actually lives."""
    stream = xray_json.build_outbound(XHTTP_URI, "proxy")["streamSettings"]
    assert stream["network"] == "xhttp"
    assert stream["xhttpSettings"]["path"] == "/abc123"
    assert stream["xhttpSettings"]["mode"] == "auto"
    assert stream["realitySettings"]["publicKey"] == "PBK"


def test_xhttp_extra_is_decoded_into_an_object():
    stream = xray_json.build_outbound(XHTTP_URI, "proxy")["streamSettings"]
    assert stream["xhttpSettings"]["extra"] == {"xPaddingBytes": "100-1000"}


def test_xhttp_malformed_extra_is_dropped_not_fatal():
    uri = XHTTP_URI.replace("extra=%7B%22xPaddingBytes%22%3A+%22100-1000%22%7D", "extra=not-json")
    stream = xray_json.build_outbound(uri, "proxy")["streamSettings"]
    assert "extra" not in stream["xhttpSettings"]
    assert stream["xhttpSettings"]["path"] == "/abc123"


def test_tcp_links_get_no_xhttp_block():
    stream = xray_json.build_outbound(REALITY, "proxy")["streamSettings"]
    assert "xhttpSettings" not in stream


def test_xhttp_joins_the_balancer():
    config = xray_json.build_balancer_config([REALITY, XHTTP_URI])
    tags = [o["tag"] for o in config["outbounds"] if o["tag"].startswith("proxy-")]
    assert len(tags) == 2
