import base64
import json
import urllib.parse

import pytest

from services import sub_gateway
from services.sub_gateway import combine_links, happ_redirect_page

US_HOST = "144.172.101.217.sslip.io"
NL_HOST = "107.189.22.160.sslip.io"


@pytest.fixture
def hy2_nodes(monkeypatch):
    """Give the known nodes a Hysteria2 password so Hy2 entries are emitted."""
    nodes = {
        US_HOST: {**sub_gateway.NODES[US_HOST], "hy2_pass": "us-secret"},
        NL_HOST: {**sub_gateway.NODES[NL_HOST], "hy2_pass": "nl-secret"},
    }
    monkeypatch.setattr(sub_gateway, "NODES", nodes)
    return nodes


def test_combine_links_passes_trojan_through():
    decoded = f"trojan://pw@{US_HOST}:8443?security=tls#US-Trojan"
    assert combine_links(decoded) == [decoded]


def test_combine_links_preserves_vless_and_trojan_order():
    vless = f"vless://uuid@{US_HOST}:443?flow=xtls-rprx-vision#US-VLESS"
    trojan = f"trojan://pw@{US_HOST}:8443?security=tls#US-Trojan"
    assert combine_links(f"{vless}\n{trojan}") == [vless, trojan]


def test_combine_links_appends_hy2_once_per_node(hy2_nodes):
    vless = f"vless://uuid@{US_HOST}:443#US-VLESS"
    trojan = f"trojan://pw@{US_HOST}:8443#US-Trojan"
    result = combine_links(f"{vless}\n{trojan}")
    hy2_entries = [uri for uri in result if uri.startswith("hysteria2://")]
    assert len(hy2_entries) == 1
    # Hy2 follows the node's first link, not the last.
    assert result[0] == vless
    assert result[1].startswith("hysteria2://us-secret@")
    assert result[2] == trojan


def test_combine_links_emits_hy2_per_distinct_node(hy2_nodes):
    us = f"trojan://pw@{US_HOST}:8443#US-Trojan"
    nl = f"vless://uuid@{NL_HOST}:2053#NL-VLESS"
    result = combine_links(f"{us}\n{nl}")
    hy2_hosts = sorted(uri.split("@", 1)[1].split(":", 1)[0] for uri in result if uri.startswith("hysteria2://"))
    assert hy2_hosts == [NL_HOST, US_HOST]


def test_combine_links_skips_hy2_for_unknown_host(hy2_nodes):
    trojan = "trojan://pw@unknown.example.com:8443#Other"
    assert combine_links(trojan) == [trojan]


def test_combine_links_skips_hy2_when_node_has_no_password():
    # Default test env leaves US_HY2_PASS empty -> no Hy2 appended.
    trojan = f"trojan://pw@{US_HOST}:8443#US-Trojan"
    assert combine_links(trojan) == [trojan]


def test_combine_links_ignores_blank_and_non_uri_lines():
    vless = f"vless://uuid@{US_HOST}:443#US"
    assert combine_links(f"\n  \n{vless}\nnot-a-link\n") == [vless]


def test_combine_links_empty_when_no_proxies():
    assert combine_links("") == []
    assert combine_links("garbage\nmore garbage") == []


def test_combine_links_appends_trojan_for_node_with_trojan_pass(monkeypatch):
    nodes = {US_HOST: {**sub_gateway.NODES[US_HOST], "hy2_pass": "", "trojan_pass": "tj", "trojan_port": 8444}}
    monkeypatch.setattr(sub_gateway, "NODES", nodes)
    vless = f"vless://uuid@{US_HOST}:443#US"
    result = combine_links(vless)
    trojans = [u for u in result if u.startswith("trojan://")]
    assert len(trojans) == 1
    assert trojans[0].startswith(f"trojan://tj@{US_HOST}:8444")
    assert "security=tls" in trojans[0] and f"sni={US_HOST}" in trojans[0]


def test_combine_links_emits_hy2_then_trojan_in_order(monkeypatch):
    nodes = {US_HOST: {**sub_gateway.NODES[US_HOST], "hy2_pass": "h", "trojan_pass": "t", "trojan_port": 8444}}
    monkeypatch.setattr(sub_gateway, "NODES", nodes)
    vless = f"vless://uuid@{US_HOST}:443#US"
    result = combine_links(vless)
    assert result[0] == vless
    assert result[1].startswith("hysteria2://h@")
    assert result[2].startswith("trojan://t@")


def test_combine_links_no_trojan_when_pass_empty():
    # Real PL node has a trojan_pass key but PL_TROJAN_PASS is empty in tests.
    vless = f"vless://uuid@78.17.154.225.sslip.io:2087#PL"
    assert combine_links(vless) == [vless]



def test_happ_redirect_page_embeds_add_deeplink():
    page = happ_redirect_page("https://sub.unlockvpn.org:8444/sub/abc123")
    assert "happ://add/https://sub.unlockvpn.org:8444/sub/abc123" in page
    assert "location.replace" in page
    assert "Открыть в Happ" in page


def test_happ_redirect_page_is_valid_html_document():
    page = happ_redirect_page("https://sub.unlockvpn.org:8444/sub/a-b_c")
    assert page.startswith("<!doctype html>")
    assert "<a href=" in page
    assert 'http-equiv="refresh"' in page


def test_fetch_upstream_prefers_remnawave_when_configured(monkeypatch):
    calls: list[str] = []

    def fake_get(url: str):
        calls.append(url)
        return ("vless://uuid@78.17.154.225.sslip.io:2088?security=reality#PL", None)

    monkeypatch.setattr(sub_gateway, "REMNAWAVE_SUB_BASE", "https://panel.example/api/sub")
    monkeypatch.setattr(sub_gateway, "_http_get_sub", fake_get)

    result = sub_gateway._fetch_upstream_sub("tok123")

    assert result is not None
    assert result[2] == "remnawave"
    assert calls == ["https://panel.example/api/sub/tok123"]


def test_fetch_upstream_falls_back_to_marzban_on_empty_remnawave(monkeypatch):
    calls: list[str] = []

    def fake_get(url: str):
        calls.append(url)
        if "panel.example" in url:
            return None  # token not on Remnawave yet (mid-migration)
        return ("vless://uuid@144.172.101.217.sslip.io:443?security=reality#US", None)

    monkeypatch.setattr(sub_gateway, "REMNAWAVE_SUB_BASE", "https://panel.example/api/sub")
    monkeypatch.setattr(sub_gateway, "MARZBAN_BASE", "https://mz.example:8443")
    monkeypatch.setattr(sub_gateway, "_http_get_sub", fake_get)

    result = sub_gateway._fetch_upstream_sub("tok123")

    assert result is not None
    assert result[2] == "marzban"
    assert calls == [
        "https://panel.example/api/sub/tok123",
        "https://mz.example:8443/sub/tok123",
    ]


def test_fetch_upstream_uses_marzban_when_remnawave_unset(monkeypatch):
    calls: list[str] = []

    def fake_get(url: str):
        calls.append(url)
        return ("vless://uuid@144.172.101.217.sslip.io:443#US", None)

    monkeypatch.setattr(sub_gateway, "REMNAWAVE_SUB_BASE", "")
    monkeypatch.setattr(sub_gateway, "MARZBAN_BASE", "https://mz.example:8443")
    monkeypatch.setattr(sub_gateway, "_http_get_sub", fake_get)

    sub_gateway._fetch_upstream_sub("tok123")

    assert calls == ["https://mz.example:8443/sub/tok123"]


# --- expiry enforcement -----------------------------------------------------

def _future_ts() -> int:
    import time

    return int(time.time()) + 3600


def test_userinfo_expired_when_expire_in_past():
    assert sub_gateway._userinfo_expired("upload=1; download=2; total=0; expire=1000000") is True


def test_userinfo_not_expired_when_expire_in_future():
    assert sub_gateway._userinfo_expired(f"upload=1; download=2; expire={_future_ts()}") is False


def test_userinfo_not_expired_when_unlimited_or_absent():
    assert sub_gateway._userinfo_expired("upload=1; expire=0") is False
    assert sub_gateway._userinfo_expired("upload=1; download=2") is False
    assert sub_gateway._userinfo_expired(None) is False


def test_build_combined_blanks_sub_when_userinfo_expired(monkeypatch):
    userinfo = "upload=0; download=0; total=0; expire=1000000"
    monkeypatch.setattr(
        sub_gateway,
        "_fetch_upstream_sub",
        lambda token: (f"vless://uuid@{US_HOST}:443#US", userinfo, "marzban"),
    )
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)

    payload, out_userinfo = sub_gateway.build_combined("tok")

    assert payload == ""
    assert out_userinfo == userinfo


def test_build_combined_blanks_sub_when_marzban_reports_inactive(monkeypatch):
    monkeypatch.setattr(
        sub_gateway,
        "_fetch_upstream_sub",
        lambda token: (f"vless://uuid@{US_HOST}:443#US", None, "marzban"),
    )
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: False)

    payload, _ = sub_gateway.build_combined("tok")

    assert payload == ""


def test_build_combined_serves_active_marzban_user(monkeypatch):
    import base64

    vless = f"vless://uuid@{US_HOST}:443#US"
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", False)
    monkeypatch.setattr(
        sub_gateway,
        "_fetch_upstream_sub",
        lambda token: (vless, f"expire={_future_ts()}", "marzban"),
    )
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)

    payload, _ = sub_gateway.build_combined("tok")

    assert base64.b64decode(payload).decode("utf-8") == vless


def test_build_combined_skips_marzban_status_check_for_remnawave(monkeypatch):
    import base64

    vless = f"vless://uuid@{US_HOST}:443#US"
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", False)
    monkeypatch.setattr(
        sub_gateway,
        "_fetch_upstream_sub",
        lambda token: (vless, None, "remnawave"),
    )

    def boom(token):
        raise AssertionError("must not query Marzban for a Remnawave sub")

    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", boom)

    payload, _ = sub_gateway.build_combined("tok")

    assert base64.b64decode(payload).decode("utf-8") == vless


def test_marzban_sub_active_fails_open_on_transport_error(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("panel down")

    monkeypatch.setattr(sub_gateway.urllib.request, "urlopen", boom)

    assert sub_gateway._marzban_sub_active("tok") is True


# --- browser vs VPN-client detection for /sub redirect ----------------------

def test_is_browser_true_for_real_browsers():
    chrome = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    safari_ios = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    assert sub_gateway._is_browser(chrome) is True
    assert sub_gateway._is_browser(safari_ios) is True


def test_supports_xray_json_only_for_known_json_clients():
    assert sub_gateway._supports_xray_json("Happ/1.0") is True
    assert sub_gateway._supports_xray_json("happ") is True
    # base64-only clients must keep the URI list
    for ua in ("v2rayNG/1.8.5", "Hiddify/2.0", "Streisand", "sing-box 1.9", "", None):
        assert sub_gateway._supports_xray_json(ua) is False, ua


def test_is_browser_false_for_vpn_clients_and_empty():
    for ua in ("v2rayNG/1.8.5", "Happ/1.0", "Hiddify/2.0", "Streisand", "clash-verge/1.0",
               "sing-box 1.9", "Shadowrocket/2.2", "v2rayTun/3", "", None):
        assert sub_gateway._is_browser(ua) is False, ua


# --- node health / авто-обход -------------------------------------------------


@pytest.fixture
def health(monkeypatch):
    """Fresh health registry with the checker enabled."""
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", True)
    monkeypatch.setattr(sub_gateway, "_probe_fails", {})
    return sub_gateway._probe_fails


def _vless(host: str, port: int = 2087) -> str:
    return f"vless://uuid@{host}:{port}?security=reality#test"


def _hy2(host: str) -> str:
    return f"hysteria2://pass@{host}:443?sni={host}#test"


def test_uri_endpoint_parses_host_and_port():
    assert sub_gateway._uri_endpoint(_vless("h.example", 2087)) == ("h.example", 2087)
    assert sub_gateway._uri_endpoint("trojan://p@h.example:8444?security=tls#x") == ("h.example", 8444)
    # no explicit port -> 443
    assert sub_gateway._uri_endpoint("vless://uuid@h.example?type=tcp#x") == ("h.example", 443)
    assert sub_gateway._uri_endpoint("not-a-uri") is None


def test_register_probe_targets_skips_udp(health):
    sub_gateway._register_probe_targets([_vless("h1", 2087), _hy2("h1")])
    assert ("h1", 2087) in health
    assert ("h1", 443) not in health  # hysteria2 is UDP, no TCP probe


def test_filter_alive_keeps_all_when_no_failures(health):
    links = [_vless("h1"), _hy2("h1")]
    sub_gateway._register_probe_targets(links)
    assert sub_gateway.filter_alive(links) == links


def test_filter_alive_drops_dead_tcp_endpoint(health):
    links = [_vless("h1"), _vless("h2")]
    sub_gateway._register_probe_targets(links)
    health[("h1", 2087)] = sub_gateway.HEALTH_FAILS
    assert sub_gateway.filter_alive(links) == [_vless("h2")]


def test_filter_alive_hy2_follows_host_level_health(health):
    links = [_vless("h1", 2087), _vless("h1", 8443), _hy2("h1"), _vless("h2"), _hy2("h2")]
    sub_gateway._register_probe_targets(links)
    # one of h1's TCP ports is dead, the other alive -> host alive, hy2 stays
    health[("h1", 2087)] = sub_gateway.HEALTH_FAILS
    kept = sub_gateway.filter_alive(links)
    assert _hy2("h1") in kept and _vless("h1", 8443) in kept
    assert _vless("h1", 2087) not in kept

    # all of h1's TCP ports dead -> host dead, hy2 dropped too
    health[("h1", 8443)] = sub_gateway.HEALTH_FAILS
    kept = sub_gateway.filter_alive(links)
    assert kept == [_vless("h2"), _hy2("h2")]


def test_filter_alive_fails_safe_when_everything_dead(health):
    links = [_vless("h1"), _hy2("h1")]
    sub_gateway._register_probe_targets(links)
    health[("h1", 2087)] = sub_gateway.HEALTH_FAILS
    # filtering would leave nothing -> serve unfiltered
    assert sub_gateway.filter_alive(links) == links


def test_filter_alive_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_probe_fails", {("h1", 2087): 99})
    links = [_vless("h1")]
    assert sub_gateway.filter_alive(links) == links


def test_auto_headers_enable_happ_autoconnect():
    assert sub_gateway.AUTO_HEADERS["subscription-autoconnect"] == "1"
    # reconnect to the last-used entry (the balancer, after first tap)
    assert sub_gateway.AUTO_HEADERS["subscription-autoconnect-type"] == "lastused"
    # auto flavor refreshes hourly so pruned dead nodes propagate fast
    assert sub_gateway.AUTO_HEADERS["profile-update-interval"] == "1"


def _reality_uri(host: str, port: int = 2087) -> str:
    return (
        f"vless://uuid-{host}@{host}:{port}?security=reality&type=tcp"
        f"&flow=xtls-rprx-vision&sni={host}&fp=firefox&pbk=PBK&sid=SID#{host}"
    )


def test_build_auto_json_returns_json_array_with_balancer_first(monkeypatch):
    links = [_reality_uri("h1"), _hy2("h1"), _reality_uri("h2")]
    monkeypatch.setattr(sub_gateway, "resolve_links", lambda token: (links, "expire=0"))

    result = sub_gateway.build_auto_json("tok")
    assert result is not None
    body, userinfo, is_json = result
    assert is_json is True and userinfo == "expire=0"

    configs = json.loads(body)
    assert configs[0]["remarks"] == "⚡️ Авто-обход"
    assert configs[0]["routing"]["balancers"][0]["strategy"]["type"] == "leastPing"
    # Hysteria rides along now: «Авто-обход» needs a UDP path to reach for when
    # the carrier drops every TCP connection at once.
    proxy_tags = [o["tag"] for o in configs[0]["outbounds"] if o["tag"].startswith("proxy-")]
    assert proxy_tags == ["proxy-0", "proxy-1", "proxy-2"]
    protocols = {o["protocol"] for o in configs[0]["outbounds"] if o["tag"].startswith("proxy-")}
    assert protocols == {"vless", "hysteria"}


def test_build_auto_json_falls_back_to_base64_without_usable_servers(monkeypatch):
    """Nothing the client can be handed as a config object — the caller must get
    the plain list rather than an empty subscription."""
    monkeypatch.setattr(sub_gateway, "resolve_links", lambda token: (["ss://whatever@h1:443"], None))
    body, userinfo, is_json = sub_gateway.build_auto_json("tok")
    assert is_json is False
    assert "ss://whatever@h1:443" in base64.b64decode(body).decode()


def test_build_auto_json_none_for_unknown_token(monkeypatch):
    monkeypatch.setattr(sub_gateway, "resolve_links", lambda token: None)
    assert sub_gateway.build_auto_json("tok") is None


def test_reorder_by_proximity_poland_first_us_last():
    # Marzban order is US, NL, PL; RU-audience order must be PL, NL, US,
    # with each location's protocols kept grouped.
    US, NL, PL = "144.172.101.217.sslip.io", "107.189.22.160.sslip.io", "78.17.154.225.sslip.io"
    links = [
        f"vless://u@{US}:443#US",
        f"hysteria2://p@{US}:443#US-Hy2",
        f"vless://u@{NL}:2053#NL",
        f"hysteria2://p@{NL}:443#NL-Hy2",
        f"vless://u@{PL}:2087#PL",
        f"trojan://p@{PL}:8444#PL-Trojan",
    ]
    out = sub_gateway.reorder_by_proximity(links)
    hosts = [sub_gateway._uri_host(u) for u in out]
    # Poland group first, Netherlands second, USA last
    assert hosts == [PL, PL, NL, NL, US, US]


def test_reorder_by_proximity_unknown_host_before_us():
    US = "144.172.101.217.sslip.io"
    links = [f"vless://u@{US}:443#US", "vless://u@other.example:443#X"]
    out = sub_gateway.reorder_by_proximity(links)
    assert sub_gateway._uri_host(out[0]) == "other.example"  # unknown ahead of US


# --- 🇷🇺→🇩🇪 cascade -----------------------------------------------------------

DE_HOST = "166.0.28.132.sslip.io"


def _de_reality(uuid: str = "uuid", port: int = 2096) -> str:
    return (
        f"vless://{uuid}@{DE_HOST}:{port}?security=reality&type=tcp"
        f"&flow=xtls-rprx-vision&sni={DE_HOST}&fp=firefox&pbk=PBK&sid=SID#🇩🇪 Германия"
    )


def test_cascade_link_targets_the_moscow_relay_reality():
    port, remark, _ = sub_gateway.CASCADE_COUNTRIES[0]
    link = sub_gateway._cascade_link(port, remark)
    # VLESS/TCP to the relay's own Reality identity (no UDP/Hy2 twin)
    assert link.startswith(f"vless://{sub_gateway.CASCADE_UUID}@{sub_gateway.RU_RELAY_HOST}:{port}")
    assert f"sni={sub_gateway.RU_RELAY_HOST}" in link
    assert f"pbk={sub_gateway.CASCADE_PBK}" in link and f"sid={sub_gateway.CASCADE_SID}" in link
    assert "flow=xtls-rprx-vision" in link
    assert "hysteria2" not in link  # RU mobile blocks UDP — VLESS only


def test_build_cascade_links_adds_one_entry_per_country():
    cascade = sub_gateway.build_cascade_links([_de_reality("abc")])
    # one 🇷🇺→<country> entry per exit, all on the relay host, distinct ports
    assert len(cascade) == len(sub_gateway.CASCADE_COUNTRIES)
    assert all(sub_gateway._uri_host(c) == sub_gateway.RU_RELAY_HOST for c in cascade)
    ports = [sub_gateway._uri_endpoint(c)[1] for c in cascade]
    assert ports == [p for p, _, _ in sub_gateway.CASCADE_COUNTRIES]


def test_build_cascade_links_empty_for_blank_sub():
    # an expired/blank sub (no links) must not get the shared-secret cascade
    assert sub_gateway.build_cascade_links([]) == []


def test_build_cascade_links_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", False)
    assert sub_gateway.build_cascade_links([_de_reality("abc")]) == []


def test_resolve_links_places_cascade_first_when_enabled(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", True)
    monkeypatch.setattr(
        sub_gateway,
        "_fetch_upstream_sub",
        lambda token: (_de_reality("u1") + "\n" + _reality_uri("78.17.154.225.sslip.io"), None, "remnawave"),
    )
    links, _ = sub_gateway.resolve_links("tok")
    # cascade (relay host) is the very first entry a user sees
    assert sub_gateway._uri_host(links[0]) == sub_gateway.RU_RELAY_HOST
    # Poland (priority 1) then Frankfurt (priority 2) among the direct nodes
    hosts = [sub_gateway._uri_host(u) for u in links]
    assert hosts.index("78.17.154.225.sslip.io") < hosts.index(DE_HOST)


def test_resolve_links_omits_cascade_when_disabled(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", False)
    monkeypatch.setattr(
        sub_gateway,
        "_fetch_upstream_sub",
        lambda token: (_de_reality("u1"), None, "remnawave"),
    )
    links, _ = sub_gateway.resolve_links("tok")
    # no relay-host entries at all; Frankfurt direct leads
    assert all(sub_gateway._uri_host(u) != sub_gateway.RU_RELAY_HOST for u in links)
    assert sub_gateway._uri_host(links[0]) == DE_HOST


# --- end-to-end prober verdicts ----------------------------------------------

def _write_health(tmp_path, monkeypatch, nodes, age_seconds=0):
    import time as _time
    path = tmp_path / "health.json"
    path.write_text(json.dumps({"checked_at": _time.time() - age_seconds, "nodes": nodes}))
    monkeypatch.setattr(sub_gateway, "NODE_HEALTH_FILE", str(path))
    return path


def test_probed_dead_host_is_dropped_even_though_tcp_answers(tmp_path, monkeypatch, health):
    """The whole point: a node can accept TCP and still pass no traffic. The
    socket check calls it healthy, so only the prober's verdict removes it."""
    _write_health(tmp_path, monkeypatch, {"h1": False, "h2": True})
    links = [_vless("h1"), _vless("h2")]
    sub_gateway._register_probe_targets(links)  # both look alive over TCP
    assert sub_gateway.filter_alive(links) == [_vless("h2")]


def test_probed_dead_host_drops_its_udp_links_too(tmp_path, monkeypatch, health):
    _write_health(tmp_path, monkeypatch, {"h1": False, "h2": True})
    links = [_vless("h1"), _hy2("h1"), _vless("h2")]
    sub_gateway._register_probe_targets(links)
    assert sub_gateway.filter_alive(links) == [_vless("h2")]


def test_stale_health_file_is_ignored(tmp_path, monkeypatch, health):
    """A stalled prober must not strip working nodes on old verdicts."""
    _write_health(tmp_path, monkeypatch, {"h1": False}, age_seconds=99999)
    links = [_vless("h1")]
    sub_gateway._register_probe_targets(links)
    assert sub_gateway.filter_alive(links) == links


def test_missing_or_broken_health_file_fails_open(tmp_path, monkeypatch, health):
    monkeypatch.setattr(sub_gateway, "NODE_HEALTH_FILE", str(tmp_path / "nope.json"))
    assert sub_gateway._probed_dead_hosts() == set()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setattr(sub_gateway, "NODE_HEALTH_FILE", str(bad))
    assert sub_gateway._probed_dead_hosts() == set()


def test_never_serves_an_empty_sub_even_if_all_probed_dead(tmp_path, monkeypatch, health):
    """Filtering everything away would leave a paying user with nothing; the
    unfiltered list is the safer failure."""
    _write_health(tmp_path, monkeypatch, {"h1": False, "h2": False})
    links = [_vless("h1"), _vless("h2")]
    sub_gateway._register_probe_targets(links)
    assert sub_gateway.filter_alive(links) == links


# --- client-facing headers ----------------------------------------------------

def test_announce_is_base64_because_headers_are_latin1():
    """Cyrillic in a raw header would break the response, so Happ's base64
    form is mandatory here, not cosmetic."""
    headers = sub_gateway._client_headers()
    assert headers["announce"].startswith("base64:")
    decoded = base64.b64decode(headers["announce"][len("base64:"):]).decode("utf-8")
    assert "Обновите" in decoded
    decoded.encode("ascii", "ignore")  # sanity: it really was non-latin1


def test_announce_respects_happ_length_limit(monkeypatch):
    monkeypatch.setattr(sub_gateway, "SUB_ANNOUNCE", "я" * 500)
    headers = sub_gateway._client_headers()
    decoded = base64.b64decode(headers["announce"][len("base64:"):]).decode("utf-8")
    assert len(decoded) == 200


def test_announce_omitted_when_blank(monkeypatch):
    monkeypatch.setattr(sub_gateway, "SUB_ANNOUNCE", "   ")
    assert "announce" not in sub_gateway._client_headers()


def test_headers_carry_support_and_site_buttons():
    headers = sub_gateway._client_headers()
    assert headers["support-url"].startswith("https://t.me/")
    assert headers["profile-web-page-url"].startswith("https://")
    assert headers["profile-title"].startswith("base64:")


# --- /hy2 flavor: Hysteria for xray-JSON clients ------------------------------

def test_hy2_flavor_forces_base64_for_a_json_client(monkeypatch):
    """Hysteria2 runs on its own core and cannot live in an xray-JSON body, so
    a Happ user served JSON never sees it. This flavor is the only way to hand
    them the Hy2 entries without giving up «Авто-обход» on the main link."""
    monkeypatch.setattr(sub_gateway, "AUTO_IN_SUB", True)
    # mirrors the handler's decision: /hy2 wins over the JSON-capable UA
    for flavor, ua, expect_json in (
        ("", "Happ/1.0", True),
        ("auto", "Happ/1.0", True),
        ("hy2", "Happ/1.0", False),
        ("hy2", "v2rayNG/1.8.5", False),
        ("", "v2rayNG/1.8.5", False),
    ):
        force_plain = flavor == "hy2"
        is_auto = flavor == "auto"
        wants_json = not force_plain and (
            is_auto or (sub_gateway.AUTO_IN_SUB and sub_gateway._supports_xray_json(ua))
        )
        assert wants_json is expect_json, (flavor, ua)


# --- Marzban's own auto-named links -------------------------------------------

def test_default_named_links_are_dropped():
    """Adding the USA node made Marzban emit eight `<node> (<user>)
    [VLESS - tcp]` links at once: duplicates of locations we already publish,
    carrying another node's keys, failing when tapped."""
    curated = f"vless://u@{US_HOST}:443?x=1#" + urllib.parse.quote("🇺🇸 США")
    auto = f"vless://u@{US_HOST}:443?x=1#" + urllib.parse.quote("USA (tg_1038449764) [VLESS - tcp]")
    auto_x = f"vless://u@{US_HOST}:2099?x=1#" + urllib.parse.quote("USA (tg_1) [VLESS - xhttp]")
    assert combine_links("\n".join([curated, auto, auto_x])) == [curated]


def test_curated_remarks_survive_the_filter():
    for remark in ("🇵🇱 Польша · Trojan", "🇩🇪 Германия · XHTTP", "⚡️ Авто-обход",
                   "🇳🇱 Нидерланды ✅ РУ сервисы"):
        uri = f"vless://u@{US_HOST}:443?x=1#" + urllib.parse.quote(remark)
        assert combine_links(uri) == [uri], remark


def test_announce_keeps_its_line_breaks():
    """A raw header cannot contain a newline at all — base64 is what lets this
    render as separate lines in Happ instead of one run-on sentence."""
    headers = sub_gateway._client_headers()
    assert "\n" not in headers["announce"], "the header itself must stay single-line"
    decoded = base64.b64decode(headers["announce"][len("base64:"):]).decode("utf-8")
    lines = decoded.split("\n")
    assert len(lines) == 4
    assert "Авто-обход" in lines[0]      # what the default entry is
    assert "Умный обход" in lines[1]     # and when to switch off it
    assert "ms" in lines[2]              # what to do when it stops working
    assert "20%" in lines[3]             # our real terms, not free days


def test_clients_refresh_often_enough_for_a_fix_to_land_same_day():
    """The update interval is also how long a routing correction — or a node the
    health prober pulled — takes to reach someone who never reopens the app."""
    import io

    class _Probe(sub_gateway.Handler):
        def __init__(self):
            self.sent = {}
            self.wfile = io.BytesIO()

        def send_response(self, code):
            pass

        def send_header(self, key, value):
            self.sent[key.lower()] = value

        def end_headers(self):
            pass

    probe = _Probe()
    probe._send(200, b"x", "text/plain")
    assert int(probe.sent["profile-update-interval"]) <= 6


def test_the_client_is_configured_for_the_user():
    """The product is pay, tap once, done. Anything that would otherwise be
    "open settings and turn this on" ships with the subscription instead."""
    headers = sub_gateway._client_headers()
    assert headers["subscription-autoconnect"] == "true"
    assert headers["subscription-autoconnect-type"] == "lastused"
    assert headers["app-auto-start"] == "true"
    assert headers["subscription-auto-update-open-enable"] == "true"
    assert headers["exclude-apns-enable"] == "true"


def test_app_headers_are_latin1_so_they_survive_as_http():
    """Header values are latin-1 on the wire; Cyrillic has to ride as base64
    (announce already does), and a stray non-ascii value would break the whole
    response rather than one setting."""
    for key, value in sub_gateway.APP_HEADERS.items():
        key.encode("latin-1")
        value.encode("latin-1")


def test_served_subscriptions_are_logged_without_leaking_the_token(capsys):
    """Two questions in a row about what a user actually received could not be
    answered because nothing recorded it. The client string is the deciding
    fact — it is what selects the JSON body over the plain list."""
    body = json.dumps([{"remarks": "⚡️ Авто-обход"}, {"remarks": "🇵🇱 Польша"}])
    sub_gateway._log_served("abcdefghijklmnop", "Happ/2.16.2/macOS", "json", body)
    line = capsys.readouterr().out
    assert "abcdefgh" in line
    assert "ijklmnop" not in line, "the token is a credential"
    assert "flavor=json" in line and "entries=2" in line
    assert "Happ/2.16.2/macOS" in line


def test_logging_survives_a_body_it_cannot_count(capsys):
    sub_gateway._log_served("tok", "curl/8", "base64", "!!not base64!!")
    assert "entries=-1" in capsys.readouterr().out


def test_the_fastest_cascade_comes_first():
    """«Авто-обход» takes one entry per host and every cascade shares the relay,
    so whichever is listed first is the one the balancer gets. Measured from
    Moscow 2026-08-04: Frankfurt 114 Mbit/s, Warsaw 75."""
    first_port, first_label, _ = sub_gateway.CASCADE_COUNTRIES[0]
    assert "Германия" in first_label, "the fastest exit must lead the list"
    assert first_port == 2096


# --- a cascade is only as alive as the exit it hands traffic to ----------------

def test_cascade_is_dropped_when_its_exit_is_down(monkeypatch):
    """Health is tracked per host and every cascade lives on the relay, so when
    Frankfurt was switched off on 2026-08-06 its direct entries were pruned
    correctly while «🇩🇪 Германия ✅ РУ сервисы» stayed — first in the list and
    first in «Авто-обход», pointing at a machine that was off."""
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: {"166.0.28.132.sslip.io"})
    import urllib.parse
    links = sub_gateway.build_cascade_links(["vless://u@h:443#x"])
    joined = urllib.parse.unquote(" ".join(links))
    assert "Германия" not in joined
    assert "Польша" in joined and "США" in joined


def test_every_cascade_survives_when_all_exits_are_up(monkeypatch):
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", set)
    links = sub_gateway.build_cascade_links(["vless://u@h:443#x"])
    assert len(links) == len(sub_gateway.CASCADE_COUNTRIES)


def test_each_cascade_declares_where_it_terminates():
    """The port alone cannot be checked against anything; the exit host can."""
    for port, label, exit_host in sub_gateway.CASCADE_COUNTRIES:
        assert isinstance(port, int)
        assert exit_host in sub_gateway.NODES, f"{label} points at an unknown exit"


def test_announce_fits_what_happ_will_show():
    """Happ truncates the announcement at 200 characters. Silent truncation
    would cut the referral line off the end without anything failing."""
    assert len(sub_gateway.SUB_ANNOUNCE.strip()) <= 200


def test_announce_tells_the_two_automatic_entries_apart():
    """The list shows «Авто-обход» and «Банки напрямую» side by side. Someone
    whose bank complains about a VPN has to be able to tell which one to pick,
    and the app gives us nowhere but this block to say so."""
    text = sub_gateway.SUB_ANNOUNCE
    assert "Авто-обход" in text
    assert "Умный обход" in text

