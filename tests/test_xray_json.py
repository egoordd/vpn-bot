import json
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
def test_build_outbound_skips_garbage():
    assert xray_json.build_outbound("not-a-uri", "proxy-0") is None
    assert xray_json.build_outbound("vless://no-host-part", "proxy-0") is None


@pytest.mark.unit
def test_hysteria_rides_in_the_json_body():
    """Every TCP entry dies together when the carrier rebinds its NAT mapping —
    the "~20 minutes, then toggle the VPN" complaint. A QUIC connection survives
    the client's address changing, so «Авто-обход» needs a UDP path in reach.
    Excluded historically because xray-JSON cannot express Hysteria2; the client
    accepts it as an outbound object, which is how it is shipped now."""
    out = xray_json.build_outbound(HY2, "proxy-0")
    assert out["protocol"] == "hysteria"
    assert out["settings"] == {"address": "144.172.101.217.sslip.io", "port": 443, "version": 2}
    stream = out["streamSettings"]
    assert stream["network"] == "hysteria"
    assert stream["hysteriaSettings"] == {"version": 2, "auth": "pass"}
    assert stream["tlsSettings"]["alpn"] == ["h3"]
    assert stream["tlsSettings"]["serverName"] == "x"


@pytest.mark.unit
def test_hysteria_can_be_switched_off(monkeypatch):
    """One env flag back to the old behaviour, in case a client core chokes on
    the block — a first entry that fails to load costs everyone their subscription."""
    monkeypatch.setattr(xray_json, "HY2_IN_JSON", False)
    assert xray_json.build_outbound(HY2, "proxy-0") is None


@pytest.mark.unit
def test_build_balancer_config_structure():
    cfg = xray_json.build_balancer_config([REALITY, HY2, TROJAN])
    assert cfg["remarks"] == "⚡️ Авто-обход"
    # all three are balanced over now, Hysteria included
    tags = [o["tag"] for o in cfg["outbounds"]]
    assert tags == ["proxy-0", "proxy-1", "proxy-2", "direct", "block", "dns-out"]
    balancer = cfg["routing"]["balancers"][0]
    assert balancer["selector"] == ["proxy-"]
    assert balancer["strategy"]["type"] == "leastPing"
    rules = cfg["routing"]["rules"]
    # Russian destinations bypass the tunnel (real IP → RU apps work, no detour)
    assert cfg["routing"]["domainStrategy"] == "IPIfNonMatch"
    # lookups are captured first, then LAN, then the country split
    assert rules[0]["outboundTag"] == "dns-out"
    private = next(r for r in rules if r.get("ip") == ["geoip:private"])
    assert private["outboundTag"] == "direct"
    ru = next(r for r in rules if r.get("ip") == ["geoip:ru"])
    assert ru["outboundTag"] == "direct"
    # everything else load-balances across the foreign nodes
    assert rules[-1]["balancerTag"] == "auto"
    assert (cfg.get("burstObservatory") or cfg["observatory"])["subjectSelector"] == ["proxy-"]
    # a socks + http inbound the client's TUN bridges to
    assert {i["protocol"] for i in cfg["inbounds"]} == {"socks", "http"}


@pytest.mark.unit
def test_build_balancer_config_none_without_servers():
    assert xray_json.build_balancer_config([]) is None


@pytest.mark.unit
def test_build_server_config_uses_uri_remark():
    cfg = xray_json.build_server_config(REALITY, 0)
    assert cfg["remarks"] == "🇺🇸 США"
    assert [o["tag"] for o in cfg["outbounds"]] == ["proxy", "direct", "block", "dns-out"]
    # RU-bypass rules first, then everything else through the picked server
    assert any(r.get("ip") == ["geoip:ru"] for r in cfg["routing"]["rules"])
    assert cfg["routing"]["rules"][-1]["outboundTag"] == "proxy"


@pytest.mark.unit
def test_build_json_subscription_balancer_first_then_servers():
    configs = xray_json.build_json_subscription([REALITY, HY2, TROJAN])
    # objects only, but Hysteria2 is now one of those objects; the control build
    # rides second while the 20-minute question is open
    assert [c["remarks"] for c in configs] == [
        "⚡️ Авто-обход", "🏦 Банки напрямую", "🇺🇸 США", "US-Hy2", "🇵🇱 Trojan",
    ]


@pytest.mark.unit
def test_build_json_subscription_empty_without_servers():
    assert xray_json.build_json_subscription([]) == []


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


def test_names_decide_before_addresses_do():
    """`AsIs` left the geoip:ru rule dead: sniffing replaces the target with the
    domain, and with nothing resolved an IP rule can never match — measured
    2026-08-03, when every Russian service outside a .ru zone rode the tunnel.
    IPIfNonMatch resolves only what no name rule already decided."""
    config = _balancer()
    routing = config["routing"]
    assert routing["domainStrategy"] == "IPIfNonMatch"
    domain_rules = [i for i, r in enumerate(routing["rules"]) if "domain" in r]
    geo_ru = next(i for i, r in enumerate(routing["rules"]) if r.get("ip") == ["geoip:ru"])
    assert domain_rules and max(domain_rules) < geo_ru, "names must be tried first"


def _quic_rule(rules):
    return next(
        (r for r in rules if r.get("network") == "udp" and r.get("port") == 443), None
    )


def test_quic_is_allowed_by_default():
    """Dropping QUIC is not a refusal an application can act on — it is silence
    it has to time out on. With the rule in place the owner got no video at all,
    on any protocol, while the same link served 100 MB at 5 MB/s over TCP, ran
    twenty parallel fetches, and fed yt-dlp real YouTube media at 4.5 MB/s. The
    browser, which prefers QUIC, buffered forever. So the default lets it pass."""
    assert _quic_rule(_balancer()["routing"]["rules"]) is None


def test_quic_can_be_refused_when_the_flag_is_set(monkeypatch):
    """Kept switchable: on a lossy mobile link UDP inside a TCP tunnel makes the
    two layers retransmit against each other, and the balancer cannot see it
    because its probe is a small TCP fetch."""
    monkeypatch.setattr(xray_json, "BLOCK_QUIC", True)
    rules = _balancer()["routing"]["rules"]
    quic = _quic_rule(rules)
    assert quic is not None and quic["outboundTag"] == "block"
    assert rules.index(quic) < len(rules) - 1, "must be decided before the catch-all"


def test_dns_still_passes_while_quic_is_blocked(monkeypatch):
    """The QUIC rule is by port, and lookups are UDP too — blocking both would
    take the client off the internet entirely."""
    monkeypatch.setattr(xray_json, "BLOCK_QUIC", True)
    rules = _balancer()["routing"]["rules"]
    dns_rule = next(i for i, r in enumerate(rules) if str(r.get("port")) == "53")
    assert dns_rule < rules.index(_quic_rule(rules))




# --- lookups ------------------------------------------------------------------

def _dns_rules(config):
    return [r for r in config["routing"]["rules"] if str(r.get("port")) == "53"]


def test_lookups_never_leave_the_device_unanswered():
    """The 2026-07-28 outage: port 53 sent `direct` left the phone, whose system
    resolver the VPN owned, and came straight back in — nothing loaded at all."""
    for config in (_balancer(), xray_json.build_server_config(REALITY, 0)):
        for rule in _dns_rules(config):
            assert rule["outboundTag"] == "dns-out", "DNS must be answered internally"


def test_dns_hijack_cannot_loop_on_itself():
    """xray's own resolver queries 1.1.1.1 over the tunnel. Those queries carry
    no inbound tag, so scoping the hijack to the local inbounds is what stops
    them from matching it again forever."""
    rules = _dns_rules(_balancer())
    assert rules, "app lookups must be captured, or the carrier answers them"
    assert set(rules[0]["inboundTag"]) == {"socks-in", "http-in"}


def test_the_device_resolver_is_never_used():
    """It does not answer for blocked names — measured empty for tiktok and
    instagram from an MTS line — so an app gets no address, opens no connection,
    and the tunnel never sees the request."""
    servers = xray_json._DNS["servers"]
    assert "localhost" not in servers
    assert not any(
        isinstance(s, dict) and s.get("address") == "localhost" for s in servers
    )


def test_russian_names_are_answered_inside_russia():
    """Otherwise RU sites resolve to a foreign edge of their CDN and the
    RU-split stops being worth having."""
    scoped = [s for s in xray_json._DNS["servers"] if isinstance(s, dict)]
    assert scoped and scoped[0]["address"] == "77.88.8.8"
    assert "regexp:\\.ru$" in scoped[0]["domains"]


def test_only_v4_addresses_are_requested():
    """The exits are IPv4-only; an AAAA answer points the app at an address the
    exit cannot reach, and the big platforms are all dual-stack."""
    assert xray_json._DNS["queryStrategy"] == "UseIPv4"


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
    pinned = next(r for r in rules if r.get("balancerTag") == "auto" and "domain" in r)
    geo_ru = next(i for i, r in enumerate(rules) if r.get("ip") == ["geoip:ru"])
    # decided by domain, before any IP rule can send it direct
    assert rules.index(pinned) < geo_ru
    joined = " ".join(pinned["domain"])
    for host in ("tiktok.com", "instagram.com", "cdninstagram.com", "fbcdn.net",
                 "googlevideo.com", "youtube.com", "ibytedtos.com", "byteoversea.com"):
        assert f"domain:{host}" in joined


def test_single_server_config_pins_the_same_domains():
    config = xray_json.build_server_config(
        "vless://uuid@h1:2096?security=reality&sni=h1&pbk=P&sid=S#h1", 0
    )
    pinned = next(r for r in config["routing"]["rules"]
                  if r.get("outboundTag") == "proxy" and "domain" in r)
    assert "domain:tiktok.com" in pinned["domain"]


def test_ru_traffic_is_matched_by_name():
    """The RU ISP resolver answers nothing for blocked domains — which is safe
    now only because blocked names are never resolved on the device: they match
    by name and are resolved at the exit."""
    rules = _balancer()["routing"]["rules"]
    ru = next(r for r in rules if any("\\.ru$" in d for d in r.get("domain", [])))
    assert ru["outboundTag"] == "direct"
    # The case that matters is a blocked platform whose CDN sits on Russian
    # *addresses* — tiktokcdn, googlevideo. Those are pinned by name ahead of
    # the geoip:ru rule; see test_blocked_platforms_still_beat_the_address_rule.
    pinned = next(r for r in rules if "domain:tiktok.com" in r.get("domain", []))
    geo_ru = next(i for i, r in enumerate(rules) if r.get("ip") == ["geoip:ru"])
    assert rules.index(pinned) < geo_ru


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


# --- the Russian split has to survive services outside the .ru zone -----------

def _direct_domains(config):
    rules = config["routing"]["rules"]
    return " ".join(next(r for r in rules if "domain" in r and r.get("outboundTag") == "direct")["domain"])


def test_russian_services_outside_the_ru_zone_go_direct():
    """Read off xray's own routing log on 2026-08-03: each of these was being
    sent abroad, which is «РУ-приложения работают не всегда» — Yandex without
    its stylesheets, Avito without its images, Okko refusing to play."""
    joined = _direct_domains(_balancer())
    for host in ("yastatic.net", "avito.st", "vk-cdn.net", "okko.tv",
                 "yandexcloud.net", "vkuservideo.net", "wbstatic.net"):
        assert f"domain:{host}" in joined, host


def test_google_and_spotify_never_take_the_direct_path():
    """Google's cache nodes sit inside Russian ISPs and Spotify refuses Russian
    addresses outright, so once addresses decide routing, both would be handed
    to a path that fails."""
    rules = _balancer()["routing"]["rules"]
    pinned = next(r for r in rules if "domain" in r and r.get("balancerTag") == "auto")
    joined = " ".join(pinned["domain"])
    for host in ("google.com", "gstatic.com", "googleapis.com",
                 "spotify.com", "scdn.co", "spotifycdn.com"):
        assert f"domain:{host}" in joined, host


def test_both_local_inbounds_can_recover_the_name():
    """Routing decides on names; an inbound that cannot sniff one sends
    everything to the catch-all, Russian services included."""
    for inbound in _balancer()["inbounds"]:
        if inbound["protocol"] in ("socks", "http"):
            assert inbound["sniffing"]["enabled"] is True


def test_no_domain_is_both_pinned_and_direct():
    """The Russian names are now settled before the pinned list is consulted, so
    a domain in both would silently escape the tunnel. Cheap to assert, and the
    consequence — a blocked platform sent out of the device — is not."""
    pinned = set(xray_json._FORCE_PROXY_DOMAINS)
    direct = set(xray_json._RU_DIRECT_DOMAINS)
    assert not (pinned & direct)


def test_russian_traffic_keeps_quic(monkeypatch):
    """It never enters the tunnel, so the reason to refuse QUIC does not apply —
    taking it away would only slow VK video and Yandex down. Checked with the
    refusal switched on, which is the only arrangement where it could bite."""
    monkeypatch.setattr(xray_json, "BLOCK_QUIC", True)
    rules = _balancer()["routing"]["rules"]
    ru_names = next(i for i, r in enumerate(rules)
                    if r.get("domain") and r.get("outboundTag") == "direct")
    quic = next(i for i, r in enumerate(rules)
                if r.get("network") == "udp" and r.get("port") == 443)
    assert ru_names < quic


def test_blocked_platforms_still_beat_the_address_rule():
    """Their CDN sits on Russian addresses; if geoip:ru got there first they
    would be sent out of the device to a frozen edge."""
    rules = _balancer()["routing"]["rules"]
    pinned = next(i for i, r in enumerate(rules) if r.get("balancerTag") == "auto")
    geo_ru = next(i for i, r in enumerate(rules) if r.get("ip") == ["geoip:ru"])
    assert pinned < geo_ru


# --- what a phone can afford --------------------------------------------------

def test_xhttp_buffers_are_capped_for_a_phone():
    """The panel ships 1 MB per chunk with 100 in flight — up to ~100 MB of
    buffers for one connection. iOS gives the whole VPN extension about 50 MB
    and kills it silently when it goes over: the tunnel then reads as connected
    and carries nothing until the app is reopened."""
    uri = (
        "vless://uuid@h1:2097?security=reality&type=xhttp&path=%2Fx&sni=h1&pbk=P&sid=S"
        "&extra=%7B%22scMaxEachPostBytes%22%3A1000000%2C%22scMaxConcurrentPosts%22%3A100%7D"
    )
    extra = xray_json.build_outbound(uri, "proxy-0")["streamSettings"]["xhttpSettings"]["extra"]
    assert extra["scMaxEachPostBytes"] <= 256 * 1024
    assert extra["scMaxConcurrentPosts"] <= 8


def test_smaller_buffers_from_the_panel_are_left_alone():
    """The cap is a ceiling, not a setting — a server that already ships modest
    values should keep them."""
    uri = (
        "vless://uuid@h1:2097?security=reality&type=xhttp&path=%2Fx&sni=h1&pbk=P&sid=S"
        "&extra=%7B%22scMaxEachPostBytes%22%3A65536%2C%22scMaxConcurrentPosts%22%3A4%7D"
    )
    extra = xray_json.build_outbound(uri, "proxy-0")["streamSettings"]["xhttpSettings"]["extra"]
    assert extra["scMaxEachPostBytes"] == 65536
    assert extra["scMaxConcurrentPosts"] == 4


def test_probes_do_not_dial_every_node_at_once():
    """Ten simultaneous handshakes a minute is a memory and radio burst on a
    sleeping phone — the shape of background work that gets an app reclaimed."""
    assert _prober(_balancer()).get("enableConcurrency") is False


# --- the control build -------------------------------------------------------

def test_the_dns_hijack_stays():
    """Tried without it and measured the answer: YouTube, Google, Spotify and
    SoundCloud stopped loading outright, because the carrier's resolver hands
    back the Russian cache addresses those services keep inside RU ISPs and the
    tunnel then dials them from abroad. Load-bearing — it stays."""
    config = _balancer()
    hijack = next(r for r in config["routing"]["rules"] if str(r.get("port")) == "53")
    assert hijack["outboundTag"] == "dns-out"
    assert "dns-out" in [o["tag"] for o in config["outbounds"]]
    assert config["dns"] == xray_json._DNS


def test_no_client_config_sets_keepalive():
    """Added in July against a carrier reclaiming idle mappings, and it looks to
    have caused the thing it was meant to fix: every entry — single servers
    included, where there is no balancer and no probes to blame — stopped after
    ~20 minutes and came back on toggling the VPN. A build without it ran past
    that mark on the same phone."""
    for config in (_balancer(), xray_json.build_server_config(REALITY, 0)):
        assert "sockopt" not in json.dumps(config)


def test_keepalive_can_be_put_back():
    """The July symptom was real; if it returns this goes back first."""
    import importlib
    import os as _os
    _os.environ["CLIENT_KEEPALIVE"] = "1"
    try:
        reloaded = importlib.reload(xray_json)
        assert "tcpKeepAliveIdle" in json.dumps(reloaded.build_server_config(REALITY, 0))
    finally:
        del _os.environ["CLIENT_KEEPALIVE"]
        importlib.reload(xray_json)


def test_the_balancer_takes_one_entry_per_exit():
    uris = [
        "vless://u@relay:2091?security=reality&sni=relay&pbk=P&sid=S#pl-cascade",
        "vless://u@relay:2096?security=reality&sni=relay&pbk=P&sid=S#de-cascade",
        "vless://u@pl:2087?security=reality&sni=pl&pbk=P&sid=S#pl",
        "vless://u@pl:2097?security=reality&type=xhttp&path=%2Fx&sni=pl&pbk=P&sid=S#pl-xhttp",
        "vless://u@de:2096?security=reality&sni=de&pbk=P&sid=S#de",
        "hysteria2://pw@pl:443?sni=pl#pl-hy2",
    ]
    picked = xray_json._balancer_selection(uris)
    assert picked == [uris[0], uris[2], uris[4], uris[5]], "one per host, Hysteria last"


def test_there_is_exactly_one_automatic_entry():
    """One working entry, no variants and no suffixes — a user picking between
    two «Авто-обход»es is a product that has not decided what it is."""
    configs = xray_json.build_json_subscription([REALITY, TROJAN])
    automatic = [c for c in configs if "Авто-обход" in c["remarks"]]
    assert [c["remarks"] for c in automatic] == ["⚡️ Авто-обход"]


# --- /split: Russian apps on foreign TLDs ---------------------------------------

def test_split_flavour_takes_russian_banks_off_the_tunnel():
    """A Russian bank reached from a German exit either refuses the session or
    drags it through an anti-fraud check, and the user reads that as «the VPN
    broke my bank». The \\.ru$ regexp never sees these, so they ride the tunnel
    today."""
    config = xray_json.build_balancer_config(
        [REALITY], xray_json.SPLIT_REMARKS, ru_apps_direct=True
    )
    direct = next(
        r for r in config["routing"]["rules"]
        if r.get("outboundTag") == "direct" and isinstance(r.get("domain"), list)
    )
    assert "domain:tbank.com" in direct["domain"]
    assert "domain:gosuslugi.gov" in direct["domain"], "the ordinary list must survive"
    assert config["remarks"] == xray_json.SPLIT_REMARKS


def test_ordinary_subscription_is_left_alone():
    """The extra names ship to volunteers first: sending a domain direct takes it
    out of the tunnel for good."""
    direct = next(
        r for r in _balancer()["routing"]["rules"]
        if r.get("outboundTag") == "direct" and isinstance(r.get("domain"), list)
    )
    assert "domain:tbank.com" not in direct["domain"]


def test_split_still_pins_blocked_platforms_to_the_tunnel():
    """Taking more names direct must not let a blocked platform out with them."""
    config = xray_json.build_balancer_config(
        [REALITY], xray_json.SPLIT_REMARKS, ru_apps_direct=True
    )
    rules = config["routing"]["rules"]
    direct = next(i for i, r in enumerate(rules)
                  if r.get("outboundTag") == "direct" and isinstance(r.get("domain"), list))
    pinned = next(i for i, r in enumerate(rules) if "domain:googlevideo.com" in (r.get("domain") or []))
    assert rules[pinned].get("balancerTag") == "auto"
    assert direct < pinned, "domestic names decided first, blocked ones still tunnelled"
    assert not set(rules[direct]["domain"]) & set(rules[pinned]["domain"])


def test_both_russian_resolvers_come_before_any_foreign_one():
    """lknpd.nalog.ru — the «Мой налог» backend — is answered by Russian
    resolvers and returns nothing to Cloudflare or Google. Asked from Moscow it
    resolves and serves 200; through the tunnel on 2026-08-11 it resolved
    nowhere and the app opened with no network. A foreign resolver cannot stand
    in for these, so the fallback has to be Russian too."""
    servers = _balancer()["dns"]["servers"]
    scoped = [s for s in servers if isinstance(s, dict)]
    plain = [s for s in servers if isinstance(s, str)]
    assert len(scoped) >= 2, "one Russian resolver is a single point of failure"
    assert all("\\.ru$" in " ".join(s["domains"]) for s in scoped)
    last_scoped = max(i for i, s in enumerate(servers) if isinstance(s, dict))
    first_plain = min(i for i, s in enumerate(servers) if isinstance(s, str))
    assert last_scoped < first_plain, "a RU name must never fall through to a foreign resolver first"
    assert plain, "foreign names still need a resolver"


def test_both_automatic_entries_ship_in_one_subscription():
    """One link carries «Авто-обход» and «Автопереключение», so a user switches
    between them in the app instead of importing a second subscription."""
    configs = xray_json.build_json_subscription([REALITY])
    assert configs[0]["remarks"] == xray_json.AUTO_REMARKS
    assert configs[1]["remarks"] == xray_json.SPLIT_REMARKS

    def direct(cfg):
        return next(r for r in cfg["routing"]["rules"]
                    if r.get("outboundTag") == "direct" and isinstance(r.get("domain"), list))

    assert "domain:tbank.com" not in direct(configs[0])["domain"]
    assert "domain:tbank.com" in direct(configs[1])["domain"]


def test_auto_stays_first_so_existing_users_keep_their_default():
    """Clients auto-connect to the first entry. Promoting the newer one would
    silently change what everyone connects to."""
    assert xray_json.build_json_subscription([REALITY])[0]["remarks"] == "⚡️ Авто-обход"
