import base64
import json
import time
import urllib.parse

import pytest

from services import sub_gateway
from services.sub_gateway import combine_links, happ_redirect_page

US_HOST = "172.86.119.133.sslip.io"
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


def test_incy_redirect_page_embeds_add_deeplink():
    page = sub_gateway.app_redirect_page("incy", "https://unlockru.site/sub/abc123")
    assert "incy://add/https://unlockru.site/sub/abc123" in page
    assert "location.replace" in page
    assert "Открыть в INCY" in page


def test_each_app_page_offers_the_other_app():
    """Ссылку в браузере открывают и те, у кого INCY, и те, у кого Happ: со
    страницы одного приложения должен быть путь в другое — иначе человек
    упирается в «не удаётся открыть» и пишет в поддержку."""
    url = "https://unlockru.site/sub/abc123"
    assert f"incy://add/{url}" in sub_gateway.app_redirect_page("happ", url)
    assert f"happ://add/{url}" in sub_gateway.app_redirect_page("incy", url)


def _open_page(path: str, monkeypatch) -> tuple[int | None, str]:
    import io

    class _Probe(sub_gateway.Handler):
        def __init__(self):
            self.path = path
            self.headers = {"User-Agent": "Mozilla/5.0 (iPhone) Safari/604.1", "Host": "unlockru.site"}
            self.code = None
            self.wfile = io.BytesIO()

        def send_response(self, code):
            self.code = code

        def send_header(self, key, value):
            pass

        def end_headers(self):
            pass

    monkeypatch.setattr(sub_gateway, "PUBLIC_BASE", "https://unlockru.site")
    probe = _Probe()
    probe.do_GET()
    return probe.code, probe.wfile.getvalue().decode("utf-8")


@pytest.mark.parametrize("app", ["happ", "incy"])
def test_app_page_imports_the_subscription_into_that_app(monkeypatch, app):
    code, page = _open_page(f"/{app}/abc123", monkeypatch)
    assert code == 200
    assert f"{app}://add/https://unlockru.site/sub/abc123" in page
    _, page = _open_page(f"/{app}/abc123/auto", monkeypatch)
    assert f"{app}://add/https://unlockru.site/sub/abc123/auto" in page


def test_app_page_rejects_a_malformed_token(monkeypatch):
    code, _ = _open_page("/incy/bad%20token!", monkeypatch)
    assert code == 404


def test_happ_redirect_page_is_valid_html_document():
    page = happ_redirect_page("https://sub.unlockvpn.org:8444/sub/a-b_c")
    assert page.startswith("<!doctype html>")
    assert "<a href=" in page
    assert 'http-equiv="refresh"' in page


def test_fetch_upstream_uses_marzban(monkeypatch):
    calls: list[str] = []

    def fake_get(url: str):
        calls.append(url)
        return ("vless://uuid@172.86.119.133.sslip.io:443#US", None)

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
        lambda token: (f"vless://uuid@{US_HOST}:443#US", userinfo),
    )
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)

    payload, out_userinfo = sub_gateway.build_combined("tok")

    assert payload == ""
    assert out_userinfo == userinfo


def test_build_combined_blanks_sub_when_marzban_reports_inactive(monkeypatch):
    monkeypatch.setattr(
        sub_gateway,
        "_fetch_upstream_sub",
        lambda token: (f"vless://uuid@{US_HOST}:443#US", None),
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
        lambda token: (vless, f"expire={_future_ts()}"),
    )
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)

    payload, _ = sub_gateway.build_combined("tok")

    # Адрес уходит клиенту прямым IP, имя остаётся в sni.
    assert base64.b64decode(payload).decode("utf-8") == (
        "vless://uuid@172.86.119.133:443?sni=172.86.119.133.sslip.io#US"
    )


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

    result = sub_gateway.build_auto_json("tok", hysteria=True)
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
    US, NL, PL = "172.86.119.133.sslip.io", "107.189.22.160.sslip.io", "78.17.154.225.sslip.io"
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
    US = "172.86.119.133.sslip.io"
    links = [f"vless://u@{US}:443#US", "vless://u@other.example:443#X"]
    out = sub_gateway.reorder_by_proximity(links)
    assert sub_gateway._uri_host(out[0]) == "other.example"  # unknown ahead of US


# --- 🇷🇺→🇩🇪 cascade -----------------------------------------------------------

DE_HOST = "178.17.58.232.sslip.io"


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
        lambda token: (_de_reality("u1") + "\n" + _reality_uri("78.17.154.225.sslip.io"), None),
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
        lambda token: (_de_reality("u1"), None),
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
    assert "РУ-сервисов" in lines[1]     # and when to switch off it
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
    so whichever is listed first is the one the balancer gets, and it should be
    the exit that moves bulk traffic fastest.

    Frankfurt held this slot on a 2026-08-04 measurement (114 Mbit/s against
    Warsaw's 75). Re-measured 2026-08-22 with three 100 MB pulls from the Moscow
    relay through each exit, Poland averaged 142 Mbit/s to Frankfurt's 126 and
    was the steadier of the two. Frankfurt keeps the latency crown (37 ms vs
    67), but a cascade user has already taken the Moscow detour and feels
    throughput, not ping."""
    first_port, first_label, _ = sub_gateway.CASCADE_COUNTRIES[0]
    assert "Польша" in first_label, "the fastest exit must lead the list"
    assert first_port == 2091


# --- a cascade is only as alive as the exit it hands traffic to ----------------

def test_cascade_is_dropped_when_its_exit_is_down(monkeypatch):
    """Health is tracked per host and every cascade lives on the relay, so when
    Frankfurt was switched off on 2026-08-06 its direct entries were pruned
    correctly while «🇩🇪 Германия ✅ РУ сервисы» stayed — first in the list and
    first in «Авто-обход», pointing at a machine that was off."""
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: {"178.17.58.232.sslip.io"})
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
    assert "РУ-сервисов" in text




# --- "never expires" has to look like a date, not like 1970 -------------------

def test_unlimited_expiry_is_sent_as_a_real_future_date():
    """An unlimited link was reported as «link has expired» when a device tried
    to add it, while the gateway had served that exact token sixteen entries,
    four times in five minutes, without an error. expire=0 means unlimited by
    convention, but it is also a valid timestamp pointing at 1970, and a client
    reading it as one sees a subscription that ran out fifty years ago."""
    out = sub_gateway._normalise_userinfo("upload=0; download=68170256201; total=0; expire=0")
    assert "expire=0;" not in out and not out.endswith("expire=0")
    assert f"expire={sub_gateway._NEVER_EXPIRES}" in out
    assert sub_gateway._userinfo_expired(out) is False


def test_a_real_expiry_is_passed_through_untouched():
    """Only unlimited accounts carry expire=0. Rewriting anything else would
    hand a lapsed subscription a future date and keep serving it."""
    past = "upload=0; download=1; total=0; expire=1000000"
    assert sub_gateway._normalise_userinfo(past) == past
    assert sub_gateway._userinfo_expired(past) is True


def test_a_zero_inside_another_number_is_not_rewritten():
    """expire=0 must match the whole value, not the leading zero of a real one."""
    live = "upload=0; download=1; total=0; expire=2000000000"
    assert sub_gateway._normalise_userinfo(live) == live


def test_missing_userinfo_stays_missing():
    assert sub_gateway._normalise_userinfo(None) is None
    assert sub_gateway._normalise_userinfo("") == ""


@pytest.mark.unit
def test_lithuania_leads_the_location_list():
    """Литва идёт первой локацией — это витрина из рекламы.

    Она обгоняет даже каскад, который выигрывает по скорости входа: место в
    списке здесь продиктовано продуктом, а не замером. Платить за это нечем —
    151 мс против 141 у Франкфурта, замер из Москвы 2026-08-31.
    """
    LT, PL, DE, US = (
        "2.59.162.34.sslip.io",
        "78.17.154.225.sslip.io",
        "178.17.58.232.sslip.io",
        "172.86.119.133.sslip.io",
    )
    links = [
        f"vless://u@{US}:2102#%F0%9F%87%BA%F0%9F%87%B8",
        f"vless://u@{PL}:2087#%F0%9F%87%B5%F0%9F%87%B1",
        f"vless://u@{DE}:2096#%F0%9F%87%A9%F0%9F%87%AA",
        f"vless://u@{LT}:2101#%F0%9F%87%B1%F0%9F%87%B9",
    ]

    hosts = [sub_gateway._uri_host(u) for u in sub_gateway.reorder_by_proximity(links)]

    assert hosts == [LT, PL, DE, US]


@pytest.mark.unit
def test_the_replacement_us_node_sorts_as_far_away_as_the_old_one():
    """Новый американский сервер должен уходить в конец, как и прежний.

    Пока его не было в таблице, он получал значение по умолчанию и всплывал в
    середину списка — впереди Германии, до которой из России вчетверо ближе.
    """
    assert sub_gateway.NODE_PRIORITY["172.86.119.133.sslip.io"] > sub_gateway.NODE_PRIORITY[
        "178.17.58.232.sslip.io"
    ]


@pytest.mark.unit
def test_device_report_folds_happ_ids_that_change_with_the_date():
    """Одно устройство Happ сообщает два идентификатора, чередуя их по дню.

    Замечено на живом журнале: один и тот же телефон присылал
    ...875576 по нечётным дням и ...875676 по чётным, ровно чередуясь.
    Без свёртки счёт устройств завышался в полтора раза — 160 против 106
    на недельной выборке, и половина клиентов выглядела бы нарушителями.
    """
    from scripts.device_report import device_key

    odd, _ = device_key("Happ/3.26.3/Android/17839452147361875576")
    even, _ = device_key("Happ/3.26.3/Android/17839452147361875676")

    assert odd == even


@pytest.mark.unit
def test_device_report_does_not_count_link_previews_as_devices():
    """Мессенджер сам открывает ссылку, когда её вставили в чат.

    Это не устройство клиента, но и не шум: сам факт означает, что ссылку
    куда-то отправили, поэтому такие обращения считаются отдельно.
    """
    from scripts.device_report import device_key

    for crawler in ("TelegramBot (like TwitterBot)", "GoogleMessages", "WhatsApp/2.0"):
        _, is_crawler = device_key(crawler)
        assert is_crawler, crawler

    _, is_crawler = device_key("Happ/5.6.0/ios/2608171408551")
    assert not is_crawler


def _panel_token(username: str) -> str:
    head = base64.urlsafe_b64encode(f"{username},1788973596".encode()).decode().rstrip("=")
    return head + "rqtbHlK660"


@pytest.fixture
def migration(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HAPP_PROVIDER_ID", "Yvxgm466")
    monkeypatch.setattr(sub_gateway, "SUB_NEW_BASE", "https://unlockru.site")


def test_new_url_goes_only_to_the_test_group(monkeypatch, migration):
    """The header moves an install for good, so a test must stay a test."""
    monkeypatch.setattr(sub_gateway, "SUB_MIGRATE_USERS", frozenset({"tg_740484324"}))
    token = _panel_token("tg_740484324")

    mine = sub_gateway._client_headers(token)
    someone_else = sub_gateway._client_headers(_panel_token("tg_111"))

    assert mine["new-url"] == f"https://unlockru.site/sub/{token}"
    assert "new-url" not in someone_else


def test_the_move_keeps_the_links_flavor(monkeypatch, migration):
    """Moving must not quietly swap «РУ сервисы напрямую» for the plain link."""
    monkeypatch.setattr(sub_gateway, "SUB_MIGRATE_USERS", frozenset({"*"}))
    token = _panel_token("tg_-555")

    headers = sub_gateway._client_headers(token, "split")

    assert headers["new-url"] == f"https://unlockru.site/sub/{token}/split"


def test_the_move_names_the_whole_address_not_just_the_host(monkeypatch, migration):
    """Old links also live on :8444 and :8446. A bare host swap keeps the port
    and sends those installs to an address nothing answers on."""
    monkeypatch.setattr(sub_gateway, "SUB_MIGRATE_USERS", frozenset({"*"}))

    headers = sub_gateway._client_headers(_panel_token("tg_-555"))

    assert "new-domain" not in headers
    assert headers["new-url"].startswith("https://unlockru.site/sub/")


def test_a_target_address_alone_migrates_nobody(monkeypatch, migration):
    monkeypatch.setattr(sub_gateway, "SUB_MIGRATE_USERS", frozenset())

    assert "new-url" not in sub_gateway._client_headers(_panel_token("tg_740484324"))


def test_star_rolls_the_move_out_to_everyone(monkeypatch, migration):
    monkeypatch.setattr(sub_gateway, "SUB_MIGRATE_USERS", frozenset({"*"}))
    token = _panel_token("tg_-555")

    assert sub_gateway._client_headers(token)["new-url"] == f"https://unlockru.site/sub/{token}"


def test_website_buyers_can_be_named_in_the_test_group(monkeypatch, migration):
    monkeypatch.setattr(sub_gateway, "SUB_MIGRATE_USERS", frozenset({"tg_-2080153529382715"}))
    token = _panel_token("tg_-2080153529382715")

    headers = sub_gateway._client_headers(token)

    assert headers["new-url"] == f"https://unlockru.site/sub/{token}"


def test_a_token_that_is_not_ours_never_migrates(monkeypatch, migration):
    monkeypatch.setattr(sub_gateway, "SUB_MIGRATE_USERS", frozenset({"tg_740484324"}))

    assert "new-url" not in sub_gateway._client_headers("not-a-panel-token")
    assert "new-url" not in sub_gateway._client_headers(None)


# --- 📶 запись для мобильного интернета в «белых списках» ------------------------
# Российские операторы периодически оставляют открытыми только разрешённые
# сервисы. Туннель переживает это, если первый узел стоит на российском адресе,
# а в рукопожатии названа разрешённая служба.

MOBILE_RELAY = "203.0.113.10"


@pytest.fixture
def mobile_relay(monkeypatch):
    monkeypatch.setattr(sub_gateway, "MOBILE_HOST", MOBILE_RELAY)
    monkeypatch.setattr(sub_gateway, "MOBILE_UUID", "mobile-uuid")
    monkeypatch.setattr(sub_gateway, "MOBILE_PBK", "mobile-pbk")
    monkeypatch.setattr(sub_gateway, "MOBILE_SID", "mobilesid")


def test_the_mobile_entry_names_a_whitelisted_service_not_our_own_host(mobile_relay):
    """Смысл записи: адрес российский, а имя в рукопожатии — разрешённой службы."""
    link = sub_gateway.build_mobile_links([_de_reality()])[0]

    assert f"@{MOBILE_RELAY}:443" in link
    assert f"sni={sub_gateway.MOBILE_SNI}" in link
    assert sub_gateway.MOBILE_SNI != MOBILE_RELAY, "маскировка своим же адресом бессмысленна"
    assert "security=reality" in link and "flow=xtls-rprx-vision" in link
    assert "pbk=mobile-pbk" in link and "sid=mobilesid" in link


def test_no_relay_no_entry(monkeypatch):
    """Код живёт в выдаче и спит, пока сервер не куплен и не прописан."""
    monkeypatch.setattr(sub_gateway, "MOBILE_HOST", "")

    assert sub_gateway.build_mobile_links([_de_reality()]) == []


def test_a_lapsed_subscription_never_receives_the_shared_mobile_secret(mobile_relay):
    assert sub_gateway.build_mobile_links([]) == []


def test_the_mobile_entry_is_not_pulled_into_the_automatic_balancer(mobile_relay):
    """Трафик в российском облаке платный: авто-режим не должен его расходовать."""
    from services import xray_json

    links = [_de_reality(), *sub_gateway.build_mobile_links([_de_reality()])]

    configs = xray_json.build_json_subscription(links, exclude_from_balancer={MOBILE_RELAY})

    balancer = configs[0]
    assert MOBILE_RELAY not in json.dumps(balancer), "запись попала в авто-режим"
    servers = json.dumps(configs[1:])
    assert MOBILE_RELAY in servers, "запись должна оставаться выбираемой вручную"


# --- учёт устройств по идентификатору приложения --------------------------------
# Тариф обещает «до 3 устройств», но до сих пор это была только надпись: одну
# ссылку можно раздать кому угодно. Приложения сами присылают идентификатор
# устройства (x-hwid), и по нему лимит можно соблюдать на выдаче.

@pytest.fixture
def device_store(tmp_path, monkeypatch):
    monkeypatch.setattr(sub_gateway, "DEVICE_DB", str(tmp_path / "devices.sqlite3"))
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT", 3)
    monkeypatch.setattr(sub_gateway, "DEVICE_IDLE_DAYS", 14)
    sub_gateway._device_store.cache_clear()
    yield
    sub_gateway._device_store.cache_clear()


def _allow(hwid: str, username: str = "tg_1") -> bool:
    return sub_gateway.device_allowed(username, hwid, model="iPhone", os_name="ios")


def test_devices_within_the_limit_are_served(device_store):
    assert [_allow(f"hw{i}") for i in range(3)] == [True, True, True]


def test_the_fourth_device_is_turned_away(device_store):
    for i in range(3):
        _allow(f"hw{i}")

    assert _allow("hw-extra") is False


def test_a_device_that_comes_back_keeps_its_place(device_store):
    for i in range(3):
        _allow(f"hw{i}")

    assert _allow("hw0") is True, "своё же устройство не должно упираться в лимит"
    assert _allow("hw-extra") is False


def test_limits_are_counted_per_subscription(device_store):
    for i in range(3):
        _allow(f"hw{i}", username="tg_1")

    assert _allow("hw-other", username="tg_2") is True


def test_a_device_nobody_used_for_weeks_frees_its_slot(device_store, monkeypatch):
    """Человек сменил телефон — слот не должен держаться вечно."""
    for i in range(3):
        _allow(f"hw{i}")
    later = time.time() + sub_gateway.DEVICE_IDLE_DAYS * 86400 + 60
    monkeypatch.setattr(sub_gateway.time, "time", lambda: later)

    assert _allow("hw-new") is True


def test_an_app_that_sends_no_identifier_is_never_blocked(device_store):
    """Часть клиентов идентификатор не шлёт — их нельзя оставить без серверов."""
    for i in range(5):
        _allow(f"hw{i}")

    assert sub_gateway.device_allowed("tg_1", "", model=None, os_name=None) is True
    assert sub_gateway.device_allowed("tg_1", None, model=None, os_name=None) is True


def test_the_limit_is_off_until_it_is_switched_on(tmp_path, monkeypatch):
    """Выкладываем спящим: включаем отдельно, посмотрев на журнал."""
    monkeypatch.setattr(sub_gateway, "DEVICE_DB", str(tmp_path / "d.sqlite3"))
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT", 0)
    sub_gateway._device_store.cache_clear()

    assert all(_allow(f"hw{i}") for i in range(10))


def test_the_owner_can_see_and_reset_someones_devices(device_store):
    _allow("hw1")
    _allow("hw2", username="tg_1")

    listed = sub_gateway.devices_of("tg_1")
    assert {d["hwid"] for d in listed} == {"hw1", "hw2"}
    assert listed[0]["model"] == "iPhone"

    sub_gateway.forget_devices("tg_1")
    assert sub_gateway.devices_of("tg_1") == []


def test_the_turned_away_device_gets_a_readable_answer_not_an_empty_list(device_store):
    """Пустой ответ приложение показывает как поломку подписки."""
    body = sub_gateway.device_limit_body()
    decoded = base64.b64decode(body).decode()

    assert decoded.count("://") == 1, "одна запись, чтобы приложению было что показать"
    assert "устройств" in urllib.parse.unquote(decoded).lower()


def test_the_gate_answers_the_extra_device_and_lets_the_rest_through(device_store):
    token = _panel_token("tg_555")
    headers = {"x-hwid": "hw-a", "x-device-model": "Pixel", "x-device-os": "android"}

    assert sub_gateway.device_gate(token, headers) is None
    for hwid in ("hw-b", "hw-c"):
        assert sub_gateway.device_gate(token, {**headers, "x-hwid": hwid}) is None

    blocked = sub_gateway.device_gate(token, {**headers, "x-hwid": "hw-d"})

    assert blocked is not None, "четвёртое устройство должно получить объяснение"
    shown = urllib.parse.unquote(base64.b64decode(blocked).decode())
    assert "устройств" in shown.lower()
    assert sub_gateway.device_gate(token, headers) is None, "своё устройство продолжает работать"


def test_the_gate_stays_out_of_the_way_without_an_identifier(device_store):
    token = _panel_token("tg_556")

    assert sub_gateway.device_gate(token, {}) is None
    assert sub_gateway.device_gate("не-наш-токен", {"x-hwid": "hw"}) is None


def test_watching_mode_counts_devices_without_turning_anyone_away(device_store, monkeypatch):
    """Сначала неделя наблюдения: цифру лимита выбираем по фактам, а не на ощупь."""
    monkeypatch.setattr(sub_gateway, "DEVICE_ENFORCE", False)

    assert all(_allow(f"hw{i}") for i in range(6)), "в наблюдении никого не отключаем"
    assert len(sub_gateway.devices_of("tg_1")) == 6, "но считаем всех, чтобы увидеть раздачу"


# --- лимит берётся из тарифа, а не один на всех ---------------------------------
# У пробника два устройства, у платных три. Панель этого не знает, знает бот:
# шлюз спрашивает у его API. Дороже всего здесь ошибиться в сторону отказа —
# человек заплатил и не получил устройство, — поэтому любая неясность трактуется
# в его пользу.

@pytest.fixture
def plan_api(device_store, monkeypatch):
    """Подменяет ответ API бота и считает обращения к нему."""

    calls: list[str] = []
    answer: dict = {"subscription": {"deviceLimit": 2}}

    class _Response:
        def __init__(self, body: bytes):
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        if isinstance(answer, Exception):
            raise answer
        return _Response(json.dumps(answer).encode())

    monkeypatch.setattr(
        sub_gateway, "DEVICE_LIMIT_API", "http://127.0.0.1:8080/web/account/by-telegram/{telegram_id}"
    )
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT_API_TOKEN", "секрет")
    monkeypatch.setattr(sub_gateway.urllib.request, "urlopen", fake_urlopen)
    sub_gateway._PLAN_LIMITS.clear()
    yield calls, lambda value: answer.update(value) if isinstance(value, dict) else None, _Response
    sub_gateway._PLAN_LIMITS.clear()


def test_the_trial_gets_the_two_devices_its_tariff_promises(plan_api):
    """Общая цифра — три; у пробника своя, и действовать должна она."""
    assert _allow("hw1", username="tg_77") is True
    assert _allow("hw2", username="tg_77") is True

    assert _allow("hw3", username="tg_77") is False


def test_the_api_is_asked_about_the_owner_of_this_subscription(plan_api):
    calls, _, _ = plan_api
    _allow("hw1", username="tg_-42")

    assert calls[0].endswith("/web/account/by-telegram/-42"), "аккаунты сайта живут под минусом"


def test_the_limit_is_remembered_rather_than_asked_every_time(plan_api):
    calls, _, _ = plan_api
    for hwid in ("hw1", "hw2", "hw3"):
        _allow(hwid, username="tg_77")

    assert len(calls) == 1, "подписка меняется редко, ходить в соседнюю службу каждый раз незачем"


def test_a_tariff_without_a_limit_blocks_nobody(plan_api, monkeypatch):
    """deviceLimit=null у тарифа означает «без ограничения»."""
    _, set_answer, _ = plan_api
    set_answer({"subscription": {"deviceLimit": None}})

    assert all(_allow(f"hw{i}", username="tg_78") for i in range(8))


def test_a_silent_api_leaves_the_paid_devices_working(plan_api, monkeypatch):
    """Соседняя служба недоступна — действует общая цифра, а не отказ."""
    monkeypatch.setattr(
        sub_gateway.urllib.request,
        "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("connection refused")),
    )

    assert [_allow(f"hw{i}", username="tg_79") for i in range(3)] == [True, True, True]
    assert _allow("hw4", username="tg_79") is False, "общая цифра всё ещё действует"


def test_a_broken_answer_does_not_turn_the_limit_into_a_refusal(plan_api):
    _, set_answer, _ = plan_api
    set_answer({"subscription": {"deviceLimit": "три"}})

    assert all(_allow(f"hw{i}", username="tg_80") for i in range(5)), "мусор в ответе — не повод отключать"


# --- «Авто-обход» в чужих приложениях -------------------------------------------
# У конкурента авто-режим работает и в INCY, у нас пока только в Happ. Чужое
# приложение проверяется на живой установке, а не тестом, поэтому цена ошибки
# здесь — настройка, а не выкладка кода.

def test_only_happ_gets_the_auto_mode_until_another_client_is_checked():
    assert sub_gateway._supports_xray_json("Happ/5.7.0/ios/2609021014549") is True
    assert sub_gateway._supports_xray_json("v2rayNG/1.8.5") is False


def test_another_client_is_added_by_a_setting_not_by_a_deploy(monkeypatch):
    monkeypatch.setattr(sub_gateway, "_XRAY_JSON_UA", sub_gateway._json_clients("happ, incy"))

    assert sub_gateway._supports_xray_json("INCY/2.1 (iPhone)") is True
    assert sub_gateway._supports_xray_json("Streisand/1.0") is False, "остальные — как раньше"


def test_an_empty_setting_leaves_everyone_on_the_plain_subscription():
    """Пустая настройка не должна означать «отдавать JSON всем»."""
    assert sub_gateway._json_clients("") == ()
    assert sub_gateway._json_clients(" , ") == ()


# --- ручное снятие лимита устройств ---------------------------------------------
# Лимит берётся из тарифа, поэтому снять его конкретному человеку можно только
# явным списком в настройках шлюза.

def test_the_owner_can_lift_the_device_limit_for_one_person(plan_api, monkeypatch):
    calls, _, _ = plan_api
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT_EXEMPT", frozenset({"tg_900"}))

    assert all(_allow(f"hw{i}", username="tg_900") for i in range(12))
    assert not any(url.endswith("/900") for url in calls), "тариф освобождённого спрашивать незачем"
    assert [_allow(f"hw{i}", username="tg_901") for i in range(3)] == [True, True, False], (
        "остальные по-прежнему живут по своему тарифу"
    )


def test_the_exemption_list_is_read_forgivingly():
    assert sub_gateway._names("tg_1, tg_2 ,,") == frozenset({"tg_1", "tg_2"})
    assert sub_gateway._names("") == frozenset(), "пустая настройка — никаких исключений"


# --- аудит 22.09.2026, GW-01: устройство учитывается только по настоящей ссылке --


def _request(token: str, hwid: str, monkeypatch, *, valid: bool, path: str | None = None):
    import io

    class _Probe(sub_gateway.Handler):
        def __init__(self):
            self.path = path or f"/sub/{token}"
            self.headers = {"User-Agent": "Happ/5.6.0/ios", "x-hwid": hwid, "x-device-os": "ios"}
            self.code = None
            self.wfile = io.BytesIO()

        def send_response(self, code):
            self.code = code

        def send_header(self, key, value):
            pass

        def end_headers(self):
            pass

    answer = ("[{}]", "upload=0; download=0; total=0; expire=0", True) if valid else None
    monkeypatch.setattr(sub_gateway, "build_auto_json", lambda token, **_: answer)
    monkeypatch.setattr(sub_gateway, "build_combined", lambda token: None)
    probe = _Probe()
    probe.do_GET()
    return probe.code


def test_a_forged_link_does_not_take_the_customers_device_slots(device_store, monkeypatch):
    """Имя в ссылке не подписано: подделать его может любой, кто знает Telegram ID.
    До 22.09 шлюз записывал устройство раньше проверки ссылки, и три поддельных
    запроса запирали клиенту подключение новых устройств."""
    token = _panel_token("tg_557")

    for hwid in ("evil-1", "evil-2", "evil-3"):
        assert _request(token, hwid, monkeypatch, valid=False) == 404

    assert sub_gateway.devices_of("tg_557") == []
    assert _request(token, "owner-phone", monkeypatch, valid=True) == 200
    assert [d["hwid"] for d in sub_gateway.devices_of("tg_557")] == ["owner-phone"]


def test_device_fields_are_capped(device_store):
    """Идентификатор и модель присылает приложение; огромные строки не должны
    раздувать базу учёта."""
    assert _allow("h" * 5000)
    stored = sub_gateway.devices_of("tg_1")[0]
    assert len(stored["hwid"]) == sub_gateway.DEVICE_FIELD_MAX
    assert _allow("h" * 5000), "то же устройство узнаётся по обрезанному идентификатору"
    assert len(sub_gateway.devices_of("tg_1")) == 1



# --- аудит 22.09.2026, GW-02/GW-03 ------------------------------------------------


def test_the_panel_certificate_is_verified_by_default():
    import ssl

    assert sub_gateway._SSL.verify_mode == ssl.CERT_REQUIRED
    assert sub_gateway._SSL.check_hostname is True


def test_a_malformed_link_never_reaches_the_panel(monkeypatch):
    called = []
    monkeypatch.setattr(sub_gateway, "build_auto_json", lambda token, **_: called.append(token))
    monkeypatch.setattr(sub_gateway, "build_combined", lambda token: called.append(token))

    code = _request("x", "hw", monkeypatch, valid=False, path="/sub/не-токен%20с%20пробелом")

    assert code == 404
    assert called == []


def test_a_flood_gets_busy_instead_of_piling_onto_the_panel(monkeypatch):
    import threading

    monkeypatch.setattr(sub_gateway, "UPSTREAM_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(sub_gateway, "UPSTREAM_SLOT_WAIT", 0.05)
    sub_gateway.UPSTREAM_SLOTS.acquire()
    try:
        assert _request(_panel_token("tg_558"), "hw", monkeypatch, valid=True) == 503
    finally:
        sub_gateway.UPSTREAM_SLOTS.release()
    assert _request(_panel_token("tg_558"), "hw", monkeypatch, valid=True) == 200


def test_hosts_can_be_kept_out_of_the_automatic_modes(monkeypatch):
    """Узел с коротким пингом и урезанным каналом не должен забирать «Авто-обход» (24.09.2026)."""
    from services import sub_gateway, xray_json

    monkeypatch.setattr(sub_gateway, "BALANCER_EXCLUDE_HOSTS", frozenset({"2.59.162.34.sslip.io"}))
    monkeypatch.setattr(sub_gateway, "MOBILE_HOST", "212.233.122.241")
    excluded = sub_gateway.balancer_exclusions()
    assert excluded == {"2.59.162.34", "212.233.122.241"}

    lt = "vless://u@2.59.162.34.sslip.io:443?security=reality&type=tcp&sni=2.59.162.34.sslip.io&pbk=K&sid=1#LT"
    nl = "vless://u@107.189.22.160.sslip.io:443?security=reality&type=tcp&sni=107.189.22.160.sslip.io&pbk=K&sid=1#NL"
    lt, nl = sub_gateway.pin_addresses([lt, nl])
    picked = xray_json._balancer_selection([lt, nl], excluded)
    assert picked == [nl]


def test_servers_are_addressed_by_ip_so_no_name_lookup_can_fail():
    """«Сервер с указанным именем хоста не удалось найти» (24.09.2026): адрес — IP, имя — только в sni."""
    reality = "vless://u@78.17.154.225.sslip.io:2087?security=reality&type=tcp&sni=78.17.154.225.sslip.io&pbk=K&sid=1#PL"
    hy2 = "hysteria2://pass@78.17.154.225.sslip.io:443?sni=78.17.154.225.sslip.io&insecure=0#PL%20Hy2"
    bare = "vless://u@178.17.58.232.sslip.io:2098?security=reality&type=xhttp&path=%2Fp&pbk=K#DE"
    foreign = "vless://u@example.com:443?security=tls&sni=example.com#X"

    pinned = sub_gateway.pin_addresses([reality, hy2, bare, foreign])

    assert pinned[0] == reality.replace("@78.17.154.225.sslip.io:", "@78.17.154.225:")
    assert pinned[1] == hy2.replace("@78.17.154.225.sslip.io:", "@78.17.154.225:")
    assert pinned[2] == "vless://u@178.17.58.232:2098?security=reality&type=xhttp&path=%2Fp&pbk=K&sni=178.17.58.232.sslip.io#DE"
    assert pinned[3] == foreign


def test_both_subscription_bodies_carry_ip_addresses(monkeypatch):
    links = [
        "vless://u@78.17.154.225.sslip.io:2087?security=reality&type=tcp&sni=78.17.154.225.sslip.io&pbk=K&sid=1#PL",
        "vless://u@178.17.58.232.sslip.io:2088?security=reality&type=tcp&sni=178.17.58.232.sslip.io&pbk=K&sid=1#DE",
    ]
    monkeypatch.setattr(sub_gateway, "resolve_links", lambda token: (links, None))

    plain, _ = sub_gateway.build_combined("tok")
    body, _, is_json = sub_gateway.build_auto_json("tok")

    decoded = base64.b64decode(plain).decode()
    assert ".sslip.io:" not in decoded and "@78.17.154.225:2087" in decoded
    assert is_json
    addresses = {
        (o["settings"].get("vnext") or o["settings"].get("servers"))[0]["address"]
        for config in json.loads(body)
        for o in config["outbounds"]
        if o.get("tag", "").startswith("proxy")
    }
    assert addresses == {"78.17.154.225", "178.17.58.232"}


def test_build_auto_json_leaves_hysteria_out_unless_asked(monkeypatch):
    """Safe by default: a caller that does not know the client's core gets the
    config every core can load."""
    links = [_reality_uri("h1"), _hy2("h1"), _reality_uri("h2")]
    monkeypatch.setattr(sub_gateway, "resolve_links", lambda token: (links, None))
    body, _, is_json = sub_gateway.build_auto_json("tok")
    assert is_json is True
    assert "hysteria" not in {o["protocol"] for c in json.loads(body) for o in c["outbounds"]}


@pytest.mark.parametrize(
    "ua, expected",
    [
        ("Happ/5.9.0/ios/2609171647606", True),
        ("Happ/5.1.0/ios/2607161200000", True),
        ("Happ/5.9.0/macos/2609171647606", True),
        ("Happ/5.0.9/ios/2607011200000", False),
        ("Happ/4.12.0/ios/2606121423635", False),
        ("Happ/4.3.0/macOS/2609151456603", False),
        ("Happ/4.4.1/Android/17903223988441985697", False),
        ("Happ/4.3.0/Windows/2609151455603", False),
        ("INCY/2.6.2/ios CFNetwork/3860.400.51 Darwin/25.3.0", False),
        ("Happ/3.9.1", False),
        ("Happ/abc/ios/1", False),
        ("v2rayNG/1.9.30", False),
        ("", False),
    ],
)
def test_hysteria_goes_only_to_client_versions_with_a_new_core(monkeypatch, ua, expected):
    """xray learned the hysteria outbound in 26.1.23; Happ from the App Store
    ships 26.6.27 from 5.1.0 on. Everything else keeps the config that loads
    everywhere. The platform is matched as the app writes it: the App Store
    build says «ios»/«macos», the separate desktop build says «macOS»."""
    monkeypatch.setattr(sub_gateway, "HY2_JSON_RULES", sub_gateway.parse_hy2_rules("happ/ios>=5.1.0, happ/macos>=5.1.0"))
    assert sub_gateway.hysteria_in_json(ua) is expected


def test_hysteria_rules_default_to_nobody(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HY2_JSON_RULES", sub_gateway.parse_hy2_rules(""))
    assert sub_gateway.hysteria_in_json("Happ/5.9.0/ios/2609171647606") is False


def test_hysteria_master_switch_still_wins(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HY2_JSON_RULES", sub_gateway.parse_hy2_rules("happ/ios>=5.1.0"))
    monkeypatch.setattr(sub_gateway, "HY2_IN_JSON", False)
    assert sub_gateway.hysteria_in_json("Happ/5.9.0/ios/2609171647606") is False


# --- тестовая подписка 03.10.2026: РУ-релей через VK Cloud ------------------------
# «✅ РУ сервисы» тестовой ссылки идут не через московский релей, а через релей на
# VK Cloud: тот же принцип (российское выходит с релея, остальное — в страну
# пункта), только страну выбирает ключ клиента, а не порт — у VK открыт один 443.

VK_IDS = {
    "78.17.154.225.sslip.io": "aaaaaaaa-0000-0000-0000-000000000001",
    "178.17.58.232.sslip.io": "aaaaaaaa-0000-0000-0000-000000000002",
    "172.86.119.133.sslip.io": "aaaaaaaa-0000-0000-0000-000000000003",
}


def _vk_relay(monkeypatch):
    monkeypatch.setattr(sub_gateway, "VK_RELAY_USERS", frozenset({"exp_ruvk_1"}))
    monkeypatch.setattr(sub_gateway, "VK_RELAY_PBK", "VKPBK")
    monkeypatch.setattr(sub_gateway, "VK_RELAY_SID", "VKSID")
    monkeypatch.setattr(sub_gateway, "VK_RELAY_IDS", dict(VK_IDS))
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", True)
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: set())


def test_vk_relay_links_pick_the_country_by_client_key(monkeypatch):
    _vk_relay(monkeypatch)
    links = sub_gateway.build_vk_relay_links(["vless://u@78.17.154.225.sslip.io:2087#PL"])
    assert len(links) == 3
    for link in links:
        assert link.startswith("vless://")
        assert "@212.233.122.241.sslip.io:443?" in link
        assert "sni=212.233.122.241.sslip.io" in link and "pbk=VKPBK" in link and "sid=VKSID" in link
        assert "max.ru" not in link, "без маскировки под max.ru"
    assert VK_IDS["78.17.154.225.sslip.io"] in links[0]
    assert urllib.parse.unquote(links[0].partition("#")[2]) == "🇵🇱 Польша ✅ РУ сервисы · VK"


def test_vk_relay_skips_a_country_whose_exit_is_down(monkeypatch):
    _vk_relay(monkeypatch)
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: {"178.17.58.232.sslip.io"})
    links = sub_gateway.build_vk_relay_links(["vless://u@78.17.154.225.sslip.io:2087#PL"])
    assert not any(VK_IDS["178.17.58.232.sslip.io"] in link for link in links)


def test_vk_relay_needs_its_keys(monkeypatch):
    _vk_relay(monkeypatch)
    monkeypatch.setattr(sub_gateway, "VK_RELAY_PBK", "")
    assert sub_gateway.build_vk_relay_links(["vless://u@78.17.154.225.sslip.io:2087#PL"]) == []


def test_the_test_link_gets_the_vk_relay_instead_of_the_moscow_one(monkeypatch):
    _vk_relay(monkeypatch)
    upstream = "\n".join(
        f"vless://u@{h}:2087?security=reality&type=tcp&sni={h}&pbk=P&sid=S#{h}"
        for h in ("78.17.154.225.sslip.io", "178.17.58.232.sslip.io")
    )
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "filter_alive", lambda links: links)
    monkeypatch.setattr(sub_gateway, "_register_probe_targets", lambda links: None)

    test_links, _ = sub_gateway.resolve_links(_panel_token("exp_ruvk_1"))
    hosts = {sub_gateway._uri_host(link) for link in test_links}
    assert "212.233.122.241.sslip.io" in hosts
    assert sub_gateway.RU_RELAY_HOST not in hosts, "московский релей тестовой ссылке не нужен"

    ordinary, _ = sub_gateway.resolve_links(_panel_token("tg_555"))
    hosts = {sub_gateway._uri_host(link) for link in ordinary}
    assert sub_gateway.RU_RELAY_HOST in hosts, "основные подписки — через обычный релей"
    assert "212.233.122.241.sslip.io" not in hosts


def test_vk_relay_sorts_where_the_moscow_relay_does():
    assert sub_gateway.NODE_PRIORITY[sub_gateway.VK_RELAY_HOST] == sub_gateway.NODE_PRIORITY[sub_gateway.RU_RELAY_HOST]


def test_experimental_account_names_are_recognised():
    assert sub_gateway._token_username(_panel_token("exp_ruvk_1")) == "exp_ruvk_1"



# --- 03.10.2026: российские приложения мимо VPN на Android -------------------------
# С 15.04.2026 крупные российские сервисы по требованию Минцифры сами ищут VPN на
# телефоне и отказываются работать (MAX, Озон, Самокат…) — маршрутизация трафика тут
# не помогает. Happ на Android умеет выводить приложения из-под VPN по списку из
# подписки; тогда приложение VPN не видит.

def test_happ_gets_the_bypass_list_when_switched_on(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HAPP_PROVIDER_ID", "Prov1234")
    monkeypatch.setattr(sub_gateway, "PER_APP_PROXY_MODE", "bypass")
    headers = sub_gateway._client_headers("tok")
    assert headers["per-app-proxy-mode"] == "bypass"
    apps = headers["per-app-proxy-list"].split(",")
    for package in ("ru.oneme.app", "ru.ozon.app.android", "ru.sbcs.store"):
        assert package in apps, package


def test_browsers_never_bypass_the_vpn():
    """Через браузер открывают заблокированные сайты — его из-под VPN выводить нельзя."""
    browsers = {
        "com.android.chrome", "com.yandex.browser", "ru.yandex.searchplugin", "org.mozilla.firefox",
        "com.opera.browser", "com.microsoft.emmx", "com.brave.browser", "com.sec.android.app.sbrowser",
    }
    assert not browsers & set(sub_gateway.PER_APP_PROXY_LIST)


def test_no_per_app_headers_until_switched_on(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HAPP_PROVIDER_ID", "Prov1234")
    monkeypatch.setattr(sub_gateway, "PER_APP_PROXY_MODE", "")
    headers = sub_gateway._client_headers("tok")
    assert "per-app-proxy-mode" not in headers and "per-app-proxy-list" not in headers


def test_per_app_headers_need_the_provider_id(monkeypatch):
    """Без providerid Happ эти заголовки не применяет — и слать их незачем."""
    monkeypatch.setattr(sub_gateway, "HAPP_PROVIDER_ID", "")
    monkeypatch.setattr(sub_gateway, "PER_APP_PROXY_MODE", "bypass")
    assert "per-app-proxy-mode" not in sub_gateway._client_headers("tok")


def test_switching_off_tells_the_app_to_stop_bypassing(monkeypatch):
    """Откат: «off» возвращает все приложения под VPN, список не шлётся."""
    monkeypatch.setattr(sub_gateway, "HAPP_PROVIDER_ID", "Prov1234")
    monkeypatch.setattr(sub_gateway, "PER_APP_PROXY_MODE", "off")
    headers = sub_gateway._client_headers("tok")
    assert headers["per-app-proxy-mode"] == "off"
    assert "per-app-proxy-list" not in headers


# --- индивидуальная подписка (04.10.2026) ---------------------------------------

def _ind(monkeypatch):
    monkeypatch.setattr(sub_gateway, "IND_USERS", frozenset({"ind_test_1"}))
    monkeypatch.setattr(sub_gateway, "IND_HY2", {"ind_test_1": "s3cret"})
    monkeypatch.setattr(sub_gateway, "IND_RU_IDS", {"ind_test_1": "11111111-2222-3333-4444-555555555555"})
    monkeypatch.setattr(sub_gateway, "CASCADE_PBK", "PBK")
    monkeypatch.setattr(sub_gateway, "CASCADE_SID", "SID")
    upstream = "\n".join([
        "vless://u@178.17.58.232.sslip.io:2096?security=reality&type=tcp&sni=178.17.58.232.sslip.io&pbk=P&sid=S#DE",
    ])
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "filter_alive", lambda links: links)
    monkeypatch.setattr(sub_gateway, "_register_probe_targets", lambda links: None)
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: set())


def test_individual_link_gets_its_own_hysteria_login_and_nothing_shared(monkeypatch):
    _ind(monkeypatch)
    links, _ = sub_gateway.resolve_links(_panel_token("ind_test_1"))
    schemes = [link.split("://")[0] for link in links]
    assert "trojan" not in schemes, "общий Trojan с паролем на всех индивидуальной ссылке не нужен"
    hy2 = [link for link in links if link.startswith("hysteria2://")]
    assert len(hy2) == 1 and hy2[0].startswith("hysteria2://ind_test_1:s3cret@78.17.154.225.sslip.io:8443")
    assert sub_gateway.RU_RELAY_HOST not in {sub_gateway._uri_host(l) for l in links}, "без общего каскада"


def test_individual_link_json_is_auto_plus_each_server(monkeypatch):
    _ind(monkeypatch)
    body, _, is_json = sub_gateway.build_auto_json(_panel_token("ind_test_1"), hysteria=True)
    configs = json.loads(body)
    assert is_json
    assert [c["remarks"] for c in configs][0] == "⚡️ Авто-обход"
    assert len(configs) == 3
    for config in configs:
        assert any(o["tag"] == "ru-exit" for o in config["outbounds"]), config["remarks"]


def test_individual_account_names_are_recognised():
    assert sub_gateway._token_username(_panel_token("ind_test_1")) == "ind_test_1"



# --- индивидуальная подписка на своих серверах (04.10.2026) ----------------------

STATIC_TOKEN = "IndStaticToken0Abcdefghijklmnop12"
STATIC_UUID = "11111111-2222-3333-4444-555555555555"


def _static_proxy(tag: str, address: str, port: int) -> dict:
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {"vnext": [{"address": address, "port": port, "users": [
            {"id": STATIC_UUID, "encryption": "none", "flow": "xtls-rprx-vision"}]}]},
        "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {
            "serverName": f"{address}.sslip.io", "publicKey": "PBK", "shortId": "ab12",
            "spiderX": "", "fingerprint": "firefox"}},
    }


def _static_profiles() -> list[dict]:
    auto = {
        "remarks": "⚡️ Авто-обход",
        "outbounds": [_static_proxy("proxy-0", "194.87.157.197", 2096),
                      _static_proxy("proxy-1", "89.125.86.10", 21443),
                      {"tag": "direct", "protocol": "freedom"}],
        "routing": {"balancers": [{"tag": "auto", "selector": ["proxy-"]}],
                    "rules": [{"type": "field", "network": "tcp,udp", "balancerTag": "auto"}]},
    }
    single = [
        {"remarks": remark, "outbounds": [_static_proxy("proxy", address, port),
                                          {"tag": "direct", "protocol": "freedom"}],
         "routing": {"rules": [{"type": "field", "network": "tcp,udp", "outboundTag": "proxy"}]}}
        for remark, address, port in (("🇩🇪 Германия", "194.87.157.197", 2096),
                                      ("🇫🇮 Резервный вход", "89.125.86.10", 21443))
    ]
    return [auto, *single]


@pytest.fixture
def static_ind(tmp_path, monkeypatch):
    """Реестр с одной ссылкой; вызов fixture(expire=…, devices=…) переписывает запись."""
    profiles = tmp_path / "ind_x.json"
    profiles.write_text(json.dumps(_static_profiles(), ensure_ascii=False), encoding="utf-8")
    registry = tmp_path / "individual.json"
    monkeypatch.setattr(sub_gateway, "IND_STATIC_FILE", str(registry))

    def write(expire: int | None = None, devices: int = 3) -> None:
        entry = {
            "name": "ind_x",
            "expire": int(time.time()) + 3 * 86400 if expire is None else expire,
            "devices": devices,
            "profiles": str(profiles),
            "title": "Индивидуальный VPN",
        }
        registry.write_text(json.dumps({STATIC_TOKEN: entry}), encoding="utf-8")

    write()
    return write


def test_static_link_is_found_only_by_its_own_token(static_ind):
    found = sub_gateway.individual_static(STATIC_TOKEN)

    assert found is not None and found.name == "ind_x" and found.devices == 3
    assert sub_gateway.individual_static("ДругойТокен") is None
    assert sub_gateway.individual_static(_panel_token("tg_1")) is None, "обычные ссылки идут в панель"


def test_static_link_registry_trouble_means_unknown_not_a_crash(static_ind, monkeypatch, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{не json", encoding="utf-8")
    monkeypatch.setattr(sub_gateway, "IND_STATIC_FILE", str(broken))
    assert sub_gateway.individual_static(STATIC_TOKEN) is None

    monkeypatch.setattr(sub_gateway, "IND_STATIC_FILE", "")
    assert sub_gateway.individual_static(STATIC_TOKEN) is None, "без реестра — выключено"


def test_static_link_gives_happ_its_profiles_and_the_end_date(static_ind):
    expire = int(time.time()) + 3 * 86400
    static_ind(expire=expire)

    body, ctype, userinfo = sub_gateway.build_static_individual(
        sub_gateway.individual_static(STATIC_TOKEN), json_ok=True
    )

    assert ctype.startswith("application/json")
    assert [c["remarks"] for c in json.loads(body)] == ["⚡️ Авто-обход", "🇩🇪 Германия", "🇫🇮 Резервный вход"]
    assert f"expire={expire}" in userinfo and "total=0" in userinfo, "срок виден, трафик без лимита"


def test_static_link_gives_other_apps_plain_server_links(static_ind):
    body, ctype, _ = sub_gateway.build_static_individual(
        sub_gateway.individual_static(STATIC_TOKEN), json_ok=False
    )
    links = base64.b64decode(body).decode().splitlines()

    assert ctype.startswith("text/plain")
    assert len(links) == 2, "Авто-обход ссылкой не выразить — только отдельные серверы"
    de = urllib.parse.urlsplit(links[0])
    query = dict(urllib.parse.parse_qsl(de.query))
    assert (de.scheme, de.username, de.hostname, de.port) == ("vless", STATIC_UUID, "194.87.157.197", 2096)
    assert query["fp"] == "firefox" and query["pbk"] == "PBK" and query["sid"] == "ab12"
    assert query["flow"] == "xtls-rprx-vision" and query["sni"] == "194.87.157.197.sslip.io"
    assert urllib.parse.unquote(de.fragment) == "🇩🇪 Германия"


def test_expired_static_link_shows_the_date_and_no_servers(static_ind):
    static_ind(expire=int(time.time()) - 60)

    body, _, userinfo = sub_gateway.build_static_individual(
        sub_gateway.individual_static(STATIC_TOKEN), json_ok=True
    )

    assert body == ""
    assert "expire=" in userinfo


def test_static_link_without_end_date_never_expires(static_ind):
    static_ind(expire=0)
    body, _, _ = sub_gateway.build_static_individual(
        sub_gateway.individual_static(STATIC_TOKEN), json_ok=True
    )
    assert len(json.loads(body)) == 3


def _static_hysteria_profile() -> dict:
    return {
        "remarks": "🇩🇪 Германия · Hysteria2",
        "outbounds": [
            {"tag": "proxy", "protocol": "hysteria",
             "settings": {"address": "194.87.157.197", "port": 443, "version": 2},
             "streamSettings": {"network": "hysteria", "hysteriaSettings": {"version": 2, "auth": "pw"},
                                "security": "tls", "tlsSettings": {"serverName": "194.87.157.197.sslip.io"}}},
            {"tag": "direct", "protocol": "freedom"},
        ],
        "routing": {"rules": [{"type": "field", "network": "tcp,udp", "outboundTag": "proxy"}]},
    }


@pytest.fixture
def static_ind_hy2(static_ind, tmp_path):
    """Та же ссылка, но среди профилей есть Hysteria2, а для прочих приложений — свои ссылки."""
    profiles = tmp_path / "ind_x.json"
    profiles.write_text(
        json.dumps([*_static_profiles(), _static_hysteria_profile()], ensure_ascii=False), encoding="utf-8"
    )
    registry = tmp_path / "individual.json"
    entry = json.loads(registry.read_text(encoding="utf-8"))[STATIC_TOKEN]
    entry["links"] = [
        f"vless://{STATIC_UUID}@194.87.157.197:2083?security=reality#%F0%9F%87%A9%F0%9F%87%AA%20VLESS",
        "hysteria2://pw@194.87.157.197:443?sni=194.87.157.197.sslip.io#Hysteria2",
    ]
    registry.write_text(json.dumps({STATIC_TOKEN: entry}), encoding="utf-8")


def test_static_link_hides_hysteria_from_apps_with_an_old_core(static_ind_hy2):
    static = sub_gateway.individual_static(STATIC_TOKEN)

    old, _, _ = sub_gateway.build_static_individual(static, json_ok=True, hysteria=False)
    new, _, _ = sub_gateway.build_static_individual(static, json_ok=True, hysteria=True)

    assert "🇩🇪 Германия · Hysteria2" not in [c["remarks"] for c in json.loads(old)], (
        "старое ядро не разбирает outbound hysteria и бросает весь импорт"
    )
    assert [c["remarks"] for c in json.loads(new)][-1] == "🇩🇪 Германия · Hysteria2"


def test_static_link_gives_other_apps_the_links_from_the_registry(static_ind_hy2):
    body, ctype, _ = sub_gateway.build_static_individual(
        sub_gateway.individual_static(STATIC_TOKEN), json_ok=False
    )
    links = base64.b64decode(body).decode().splitlines()

    assert ctype.startswith("text/plain")
    assert [urllib.parse.urlsplit(link).scheme for link in links] == ["vless", "hysteria2"], (
        "ссылки из реестра как есть: Hysteria2 и XHTTP из профилей не вывести"
    )


def test_static_link_registry_links_must_be_a_list_of_strings(static_ind, tmp_path):
    registry = tmp_path / "individual.json"
    entry = json.loads(registry.read_text(encoding="utf-8"))[STATIC_TOKEN]
    entry["links"] = "vless://не-список"
    registry.write_text(json.dumps({STATIC_TOKEN: entry}), encoding="utf-8")

    assert sub_gateway.individual_static(STATIC_TOKEN) is None, "испорченная запись — как неизвестная"


def test_handler_gives_hysteria_only_to_the_apps_the_rule_names(static_ind_hy2, monkeypatch):
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: None)
    monkeypatch.setattr(sub_gateway, "HY2_JSON_RULES", sub_gateway.parse_hy2_rules("happ/ios>=5.1.0"))
    monkeypatch.setattr(sub_gateway, "_XRAY_JSON_UA", ("happ", "incy"))

    def remarks(ua: str) -> list[str]:
        handler = _FakeHandler(f"/sub/{STATIC_TOKEN}", {"User-Agent": ua})
        handler.do_GET()
        return [c["remarks"] for c in json.loads(handler.sent["body"])]

    assert "🇩🇪 Германия · Hysteria2" in remarks("Happ/5.9.0/ios/2609171647606")
    assert "🇩🇪 Германия · Hysteria2" not in remarks("Happ/4.4.1/android")
    assert "🇩🇪 Германия · Hysteria2" not in remarks("INCY/2.6.2/ios CFNetwork/1.0")


def test_static_link_counts_devices_against_its_own_limit(static_ind, device_store):
    static_ind(devices=2)
    static = sub_gateway.individual_static(STATIC_TOKEN)

    def gate(hwid: str) -> str | None:
        return sub_gateway.device_gate(
            STATIC_TOKEN, {"x-hwid": hwid}, username=static.name, limit=static.devices
        )

    assert gate("hw-a") is None and gate("hw-b") is None
    assert gate("hw-c") is not None, "третье устройство при лимите 2 получает объяснение"
    assert gate("hw-a") is None, "своё устройство продолжает работать"


class _FakeHandler(sub_gateway.Handler):
    """Обработчик без сокета: путь и заголовки на входе, ответ — в полях."""

    def __init__(self, path: str, headers: dict):  # noqa: D401 — без super(): сокета нет
        self.path = path
        self.headers = headers
        self.sent: dict = {}

    def _send(self, code, body, ctype, extra=None):
        self.sent = {"code": code, "body": body, "ctype": ctype, "extra": extra or {}}


def test_handler_serves_the_static_link_without_asking_the_panel(static_ind, monkeypatch):
    def no_panel(token):
        raise AssertionError("индивидуальную ссылку панель не знает — не спрашивать")

    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", no_panel)
    monkeypatch.setattr(sub_gateway, "SUB_ANNOUNCE", "🎁 Реферальная программа")
    handler = _FakeHandler(f"/sub/{STATIC_TOKEN}", {"User-Agent": "Happ/3.5.0/ios"})

    handler.do_GET()

    assert handler.sent["code"] == 200
    assert len(json.loads(handler.sent["body"])) == 3
    extra = handler.sent["extra"]
    assert "expire=" in extra["subscription-userinfo"]
    title = base64.b64decode(extra["profile-title"].removeprefix("base64:")).decode()
    assert title == "Индивидуальный VPN"
    assert "announce" not in extra, "общие объявления (рефералка, пробник) не для этого заказа"


def test_handler_turns_away_the_device_over_the_static_limit(static_ind, device_store):
    static_ind(devices=1)
    _FakeHandler(f"/sub/{STATIC_TOKEN}", {"User-Agent": "Happ/3.5.0/ios", "x-hwid": "a"}).do_GET()
    second = _FakeHandler(f"/sub/{STATIC_TOKEN}", {"User-Agent": "Happ/3.5.0/ios", "x-hwid": "b"})

    second.do_GET()

    shown = urllib.parse.unquote(base64.b64decode(second.sent["body"]).decode())
    assert "устройств" in shown.lower()


# --- ссылки без нашей марки (просьба заказчика 04.10.2026) -----------------------

def test_unbranded_link_gets_a_neutral_title_and_no_announcement(monkeypatch):
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_fi_trial"}))
    monkeypatch.setattr(sub_gateway, "UNBRANDED_TITLE", "VPN")
    monkeypatch.setattr(sub_gateway, "SUB_ANNOUNCE", "🎁 Друг по вашей ссылке — 20%")

    headers = sub_gateway._client_headers(_panel_token("corp_fi_trial"))

    title = base64.b64decode(headers["profile-title"].removeprefix("base64:")).decode()
    assert title == "VPN"
    assert "announce" not in headers


def test_other_links_keep_the_brand_and_the_announcement(monkeypatch):
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_fi_trial"}))
    monkeypatch.setattr(sub_gateway, "SUB_ANNOUNCE", "🎁 Друг по вашей ссылке — 20%")

    for name in ("corp_fi_1", "tg_1"):
        headers = sub_gateway._client_headers(_panel_token(name))
        assert headers["profile-title"] == sub_gateway.PROFILE_TITLE_HEADER, name
        assert "announce" in headers, name


def test_unbranded_link_over_the_device_limit_is_not_branded_either(monkeypatch, device_store):
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_fi_trial"}))
    monkeypatch.setattr(sub_gateway, "UNBRANDED_TITLE", "VPN")
    handler = _FakeHandler("/sub/x", {})

    handler._send_device_limit(_panel_token("corp_fi_trial"), "Happ/3.5.0/ios", "Ym9keQ==")

    title = handler.sent["extra"]["profile-title"].removeprefix("base64:")
    assert base64.b64decode(title).decode() == "VPN"


# --- 🇩🇪 Германия через польский релей (09.10.2026) ---------------------------
# Немецкий сервер недоступен из российских сетей: прямые пункты выключены в
# панели, а обычной подписке выдаётся вход на польском сервере, который
# пересылает всё в Германию — выход немецкий, к немецкому адресу клиент не ходит.


@pytest.fixture
def de_via(monkeypatch):
    monkeypatch.setattr(sub_gateway, "DE_VIA_HOST", "2.59.162.34.sslip.io")
    monkeypatch.setattr(sub_gateway, "DE_VIA_PORT", 2120)
    monkeypatch.setattr(sub_gateway, "DE_VIA_UUID", "via-uuid")
    monkeypatch.setattr(sub_gateway, "DE_VIA_PBK", "via-pbk")
    monkeypatch.setattr(sub_gateway, "DE_VIA_SID", "via-sid")
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: set())


def test_de_via_link_targets_the_relay_with_its_own_reality(de_via):
    [link] = sub_gateway.build_de_via_links([_vless("78.17.154.225.sslip.io")])

    assert link.startswith("vless://via-uuid@2.59.162.34.sslip.io:2120?")
    assert "sni=2.59.162.34.sslip.io" in link and "pbk=via-pbk" in link and "sid=via-sid" in link
    assert "flow=xtls-rprx-vision" in link and "fp=firefox" in link
    assert urllib.parse.unquote(link.rsplit("#", 1)[-1]) == "🇩🇪 Германия"


def test_de_via_is_absent_for_a_blank_subscription(de_via):
    assert sub_gateway.build_de_via_links([]) == []


def test_de_via_is_off_until_configured(de_via, monkeypatch):
    monkeypatch.setattr(sub_gateway, "DE_VIA_UUID", "")

    assert sub_gateway.build_de_via_links([_vless("78.17.154.225.sslip.io")]) == []


def test_de_via_is_dropped_when_the_german_exit_is_down(de_via, monkeypatch):
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: {sub_gateway.DE_VIA_EXIT_HOST})

    assert sub_gateway.build_de_via_links([_vless("78.17.154.225.sslip.io")]) == []


def test_regular_subscription_gets_germany_through_the_relay(de_via, monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (_vless("78.17.154.225.sslip.io"), None))

    links, _ = sub_gateway.resolve_links("tok")

    assert ("2.59.162.34.sslip.io", 2120) in {sub_gateway._uri_endpoint(link) for link in links}


def test_corporate_subscription_never_gets_the_shared_germany_entry(de_via, monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "CORP_USERS", frozenset({"corp_fi_1"}))
    monkeypatch.setattr(sub_gateway, "CORP_HOSTS", frozenset({"78.17.84.88.sslip.io"}))
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (_vless("78.17.84.88.sslip.io", 2111), None))
    token = base64.urlsafe_b64encode(b"corp_fi_1,1788973596").decode().rstrip("=") + "rqtbHlK660"

    links, _ = sub_gateway.resolve_links(token)

    assert links and ("2.59.162.34.sslip.io", 2120) not in {sub_gateway._uri_endpoint(link) for link in links}


def test_trojan_uri_pins_firefox_fingerprint():
    # Без отпечатка или с chrome ТСПУ глушит Trojan после нескольких соединений.
    node = {"flag": "🇵🇱", "name": "Польша", "hy2_host": "1.2.3.4.sslip.io",
            "trojan_port": 8444, "trojan_pass": "pw"}
    uri = sub_gateway._trojan_uri(node)
    query = dict(urllib.parse.parse_qsl(uri.split("?", 1)[1].split("#", 1)[0]))
    assert query["fp"] == "firefox"
    assert query["sni"] == "1.2.3.4.sslip.io"
    assert query["security"] == "tls"


def test_trojan_json_outbound_gets_firefox_fingerprint():
    from services import xray_json
    node = {"flag": "🇵🇱", "name": "Польша", "hy2_host": "1.2.3.4.sslip.io",
            "trojan_port": 8444, "trojan_pass": "pw"}
    query = dict(urllib.parse.parse_qsl(
        sub_gateway._trojan_uri(node).split("?", 1)[1].split("#", 1)[0]))
    stream = xray_json._stream_settings(query)
    assert stream["tlsSettings"]["fingerprint"] == "firefox"


# --- своё название и свой лимит для ручных ссылок (11.10.2026) --------------------

def test_link_with_its_own_title_shows_it_instead_of_ours(monkeypatch):
    monkeypatch.setattr(sub_gateway, "SUB_TITLES", {"corp_unl_vpn": "UNL VPN", "corp_unl_trial": "UNL VPN trial"})
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_unl_vpn", "corp_unl_trial"}))
    monkeypatch.setattr(sub_gateway, "SUB_ANNOUNCE", "🎁 Друг по вашей ссылке — 20%")

    for name, title in (("corp_unl_vpn", "UNL VPN"), ("corp_unl_trial", "UNL VPN trial")):
        headers = sub_gateway._client_headers(_panel_token(name))
        assert base64.b64decode(headers["profile-title"].removeprefix("base64:")).decode() == title
        assert "announce" not in headers, name


def test_own_title_does_not_touch_other_links(monkeypatch):
    monkeypatch.setattr(sub_gateway, "SUB_TITLES", {"corp_unl_vpn": "UNL VPN"})
    headers = sub_gateway._client_headers(_panel_token("tg_1"))
    assert headers["profile-title"] == sub_gateway.PROFILE_TITLE_HEADER


def test_manual_link_gets_its_own_device_limit_without_asking_the_bot(monkeypatch):
    monkeypatch.setattr(sub_gateway, "MANUAL_DEVICE_LIMITS", {"corp_unl_vpn": 5})
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT_API", "http://127.0.0.1:1/never-called/{telegram_id}")
    monkeypatch.setattr(sub_gateway, "_PLAN_LIMITS", {})

    assert sub_gateway.plan_device_limit("corp_unl_vpn") == 5


# --- точечные исключения для отдельных ссылок (11.10.2026) -------------------------

def test_shared_corp_host_is_shown_only_to_the_named_link(monkeypatch):
    links = [_vless("78.17.84.88.sslip.io", 2111), _vless("89.125.81.96.sslip.io", 2113), _vless("107.189.22.160.sslip.io", 2053)]
    monkeypatch.setattr(sub_gateway, "CORP_HOSTS", frozenset({"78.17.84.88.sslip.io", "89.125.81.96.sslip.io"}))

    shown = sub_gateway.corp_filter(links, corporate=False, shared=frozenset({"89.125.81.96.sslip.io"}))
    default = sub_gateway.corp_filter(links, corporate=False)

    assert {sub_gateway._uri_host(link) for link in shown} == {"89.125.81.96.sslip.io", "107.189.22.160.sslip.io"}
    assert {sub_gateway._uri_host(link) for link in default} == {"107.189.22.160.sslip.io"}


def test_hidden_exit_removes_direct_relay_and_cascade_entries(de_via, monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", True)
    monkeypatch.setattr(sub_gateway, "DE_VIA_EXIT_HOST", "178.17.58.232.sslip.io")
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "USER_HIDDEN_EXITS", {"corp_unl_vpn": frozenset({"178.17.58.232.sslip.io"})})
    upstream = _vless("78.17.154.225.sslip.io") + "\n" + _vless("178.17.58.232.sslip.io", 2096)
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))

    links, _ = sub_gateway.resolve_links(_panel_token("corp_unl_vpn"))
    names = [urllib.parse.unquote(link.rsplit("#", 1)[-1]) for link in links]
    endpoints = {sub_gateway._uri_endpoint(link) for link in links}

    assert ("178.17.58.232.sslip.io", 2096) not in endpoints
    assert ("2.59.162.34.sslip.io", 2120) not in endpoints, "Германия через польский релей спрятана"
    assert not any("Германия" in n for n in names), names
    assert any("Польша ✅ РУ сервисы" in n for n in names), "остальные каскады на месте"


def test_other_links_keep_germany_when_one_link_hides_it(de_via, monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "USER_HIDDEN_EXITS", {"corp_unl_vpn": frozenset({"178.17.58.232.sslip.io"})})
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (_vless("78.17.154.225.sslip.io"), None))

    links, _ = sub_gateway.resolve_links(_panel_token("tg_1"))

    assert ("2.59.162.34.sslip.io", 2120) in {sub_gateway._uri_endpoint(link) for link in links}


def _xhttp(host: str, port: int = 2100) -> str:
    return f"vless://uuid@{host}:{port}?type=xhttp&security=reality#xhttp"


def test_compact_link_keeps_one_reality_entry_per_server(hy2_nodes, monkeypatch):
    """«UNL VPN» (11.10.2026): по пункту на страну — без XHTTP, Hy2, Trojan и каскадов."""
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", True)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "COMPACT_USERS", frozenset({"corp_unl_vpn"}))
    upstream = "\n".join([_vless(NL_HOST), _xhttp(NL_HOST), _xhttp(US_HOST), _vless(US_HOST, 2102)])
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))

    links, _ = sub_gateway.resolve_links(_panel_token("corp_unl_vpn"))

    assert sorted(sub_gateway._uri_endpoint(link) for link in links) == sorted([(NL_HOST, 2087), (US_HOST, 2102)])


def test_compact_link_shows_auto_ru_mode_and_one_entry_per_server(hy2_nodes, monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "COMPACT_USERS", frozenset({"corp_unl_vpn"}))
    upstream = "\n".join([_vless(NL_HOST), _xhttp(NL_HOST), _vless(US_HOST, 2102)])
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))

    body, _, is_json = sub_gateway.build_auto_json(_panel_token("corp_unl_vpn"), hysteria=True)
    configs = json.loads(body)

    assert is_json
    assert len(configs) == 4, [c["remarks"] for c in configs]
    assert [o["protocol"] for o in configs[0]["outbounds"] if o["tag"].startswith("proxy-")] == ["vless", "vless"]


def test_other_links_keep_every_protocol_when_one_link_is_compact(hy2_nodes, monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "COMPACT_USERS", frozenset({"corp_unl_vpn"}))
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (_vless(NL_HOST) + "\n" + _xhttp(NL_HOST), None))

    links, _ = sub_gateway.resolve_links(_panel_token("tg_1"))

    assert {link.split("://", 1)[0] for link in links} >= {"vless", "hysteria2"}
    assert any("type=xhttp" in link for link in links)


def test_compact_link_names_the_country_without_a_server_number(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "COMPACT_USERS", frozenset({"corp_unl_vpn"}))
    fi2 = "vless://uuid@89.125.81.96.sslip.io:2113?security=reality#" + urllib.parse.quote("🇫🇮 Финляндия 2")
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (fi2, None))

    links, _ = sub_gateway.resolve_links(_panel_token("corp_unl_vpn"))

    assert [urllib.parse.unquote(link.rsplit("#", 1)[-1]) for link in links] == ["🇫🇮 Финляндия"]


# --- «Марат VPN» (12.10.2026): настройки по шаблону имени «corp_mrt_*» -------

MRT = "corp_mrt_123456789"


def test_title_and_unbranding_apply_to_a_name_pattern(monkeypatch):
    monkeypatch.setattr(sub_gateway, "SUB_TITLES", {"corp_mrt_*": "Марат VPN"})
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_mrt_*"}))
    monkeypatch.setattr(sub_gateway, "SUPPORT_URL", "https://t.me/unlock_support_bot")
    monkeypatch.setattr(sub_gateway, "PROFILE_WEB_PAGE_URL", "https://unlockproject.site")
    monkeypatch.setattr(sub_gateway, "SUB_ANNOUNCE", "UnLock: реферальная программа")

    headers = sub_gateway._client_headers(_panel_token(MRT))
    title = base64.b64decode(headers["profile-title"].removeprefix("base64:")).decode()

    assert title == "Марат VPN"
    assert not any("unlock" in str(v).lower() for v in headers.values()), headers


def test_ordinary_links_keep_support_and_site(monkeypatch):
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_mrt_*"}))
    monkeypatch.setattr(sub_gateway, "SUPPORT_URL", "https://t.me/unlock_support_bot")
    monkeypatch.setattr(sub_gateway, "PROFILE_WEB_PAGE_URL", "https://unlockproject.site")

    headers = sub_gateway._client_headers(_panel_token("tg_1"))

    assert headers["support-url"] == "https://t.me/unlock_support_bot"
    assert headers["profile-web-page-url"] == "https://unlockproject.site"


def test_device_limit_follows_a_name_pattern(monkeypatch):
    monkeypatch.setattr(sub_gateway, "MANUAL_DEVICE_LIMITS", {"corp_mrt_*": 2})
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT_API", "")
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT", 5)

    assert sub_gateway.plan_device_limit(MRT) == 2
    assert sub_gateway.plan_device_limit("corp_other") == 5


def test_compact_shared_and_hidden_follow_a_name_pattern(hy2_nodes, monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "CORP_HOSTS", frozenset({"89.125.81.96.sslip.io"}))
    monkeypatch.setattr(sub_gateway, "COMPACT_USERS", frozenset({"corp_mrt_*"}))
    monkeypatch.setattr(sub_gateway, "USER_SHARED_CORP_HOSTS", {"corp_mrt_*": frozenset({"89.125.81.96.sslip.io"})})
    monkeypatch.setattr(sub_gateway, "USER_HIDDEN_EXITS", {"corp_mrt_*": frozenset({US_HOST})})
    upstream = "\n".join([_vless(NL_HOST), _xhttp(NL_HOST), _vless(US_HOST, 2102), _vless("89.125.81.96.sslip.io", 2113)])
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))

    links, _ = sub_gateway.resolve_links(_panel_token(MRT))

    assert sorted(sub_gateway._uri_endpoint(link) for link in links) == sorted(
        [(NL_HOST, 2087), ("89.125.81.96.sslip.io", 2113)]
    )


def test_redirect_page_uses_the_brand_base_and_title(monkeypatch):
    monkeypatch.setattr(sub_gateway, "SUB_TITLES", {"corp_mrt_*": "Марат VPN"})
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_mrt_*"}))
    monkeypatch.setattr(sub_gateway, "SUB_BASES", {"corp_mrt_*": "https://m.example.test"})
    monkeypatch.setattr(sub_gateway, "PUBLIC_BASE", "https://unlockru.site")
    token = _panel_token(MRT)

    assert sub_gateway.public_base_for(token, "gw.example") == "https://m.example.test"
    assert sub_gateway.public_base_for(_panel_token("tg_1"), "gw.example") == "https://unlockru.site"
    page = sub_gateway.app_redirect_page("happ", f"https://m.example.test/sub/{token}", title=sub_gateway.page_title(token))
    assert "<title>Марат VPN</title>" in page and "unlock" not in page.lower()


# --- 12.10.2026: Финляндия-3 · Hysteria2 только в «Авто-обходе» наших подписок ---

FI3_AUTO = "hysteria2://unl_auto:pw@89.125.86.10.sslip.io:443?sni=89.125.86.10.sslip.io&insecure=0#fi3"


def _auto_configs(monkeypatch, username):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "AUTO_HY2_URIS", (FI3_AUTO,))
    monkeypatch.setattr(sub_gateway, "CORP_HOSTS", frozenset({"89.125.86.10.sslip.io"}))
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (_vless(NL_HOST) + "\n" + _vless(US_HOST, 2102), None))
    body, _, is_json = sub_gateway.build_auto_json(_panel_token(username), hysteria=True)
    assert is_json
    return json.loads(body)


def test_auto_gets_the_extra_hysteria_for_our_subscriptions(monkeypatch):
    configs = _auto_configs(monkeypatch, "tg_1")
    auto = json.dumps(configs[0])
    assert "89.125.86.10" in auto and '"hysteria"' in auto
    assert not any("89.125.86.10" in json.dumps(c) for c in configs[2:]), "отдельным пунктом её нет"


def test_corporate_and_individual_links_do_not_get_it(monkeypatch):
    for name in ("corp_unl_vpn", "ind_de_2"):
        configs = _auto_configs(monkeypatch, name)
        assert not any("89.125.86.10" in json.dumps(c) for c in configs), name


NLH1_AUTO = "hysteria2://unl_auto:pw2@13.141.51.245.sslip.io:443?sni=13.141.51.245.sslip.io&insecure=0#nlh1"


def test_auto_takes_several_extra_hysteria_servers_from_the_setting(monkeypatch):
    uris = sub_gateway._uri_list(f"{NLH1_AUTO}, {FI3_AUTO},")
    assert uris == (NLH1_AUTO, FI3_AUTO)
    monkeypatch.setattr(sub_gateway, "AUTO_HY2_URIS", uris)
    assert [u.split("@")[1].split(":")[0] for u in sub_gateway.auto_udp_for("tg_1")] == ["13.141.51.245", "89.125.86.10"]
    assert sub_gateway.auto_udp_for("corp_unl_vpn") == [] and sub_gateway.auto_udp_for("ind_de_2") == []


def test_both_extra_hysteria_servers_reach_auto_but_not_the_list(monkeypatch):
    configs = _auto_configs(monkeypatch, "tg_1")
    monkeypatch.setattr(sub_gateway, "AUTO_HY2_URIS", (NLH1_AUTO, FI3_AUTO))
    body, _, _ = sub_gateway.build_auto_json(_panel_token("tg_1"), hysteria=True)
    configs = json.loads(body)
    auto = json.dumps(configs[0])
    assert "13.141.51.245" in auto and "89.125.86.10" in auto
    assert not any("13.141.51.245" in json.dumps(c) for c in configs[2:]), "отдельным пунктом его нет"


# --- 12.10.2026: входы gRPC/WebSocket и «Авто-обход» как у конкурента ---

def _compat(monkeypatch, users=frozenset({"tg_740484324"})):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "COMPAT_NODES", {NL_HOST: (443, 2083), US_HOST: (443, 443)})
    monkeypatch.setattr(sub_gateway, "COMPAT_TROJAN_PASS", "tp")
    monkeypatch.setattr(sub_gateway, "COMPAT_VLESS_UUID", "11111111-2222-3333-4444-555555555555")
    monkeypatch.setattr(sub_gateway, "COMPAT_USERS", users)
    monkeypatch.setattr(sub_gateway, "AUTO_HY2_URIS", ())
    upstream = "\n".join([_vless(NL_HOST), _vless(US_HOST, 2102), _vless("78.17.154.225.sslip.io", 2087)])
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))


def test_compat_entries_are_listed_for_compat_users(monkeypatch):
    _compat(monkeypatch)
    links, _ = sub_gateway.resolve_links(_panel_token("tg_740484324"))
    names = [urllib.parse.unquote(l.rsplit("#", 1)[-1]) for l in links]
    assert any(n.endswith("· gRPC") for n in names) and any(n.endswith("· WS") for n in names), names
    assert sum(1 for l in links if "serviceName=trgrpc" in l) == 2


def test_other_users_do_not_see_compat_entries(monkeypatch):
    _compat(monkeypatch)
    links, _ = sub_gateway.resolve_links(_panel_token("tg_1"))
    assert not any("trgrpc" in l or "realtime" in l for l in links)


def test_compat_auto_pool_uses_new_transports_and_competitor_strategy(monkeypatch):
    _compat(monkeypatch)
    body, _, _ = sub_gateway.build_auto_json(_panel_token("tg_740484324"), hysteria=True)
    auto = json.loads(body)[0]
    proxies = [o for o in auto["outbounds"] if o["tag"].startswith("proxy-")]
    nets = sorted({o["streamSettings"]["network"] for o in proxies})
    assert nets == ["grpc", "ws"], nets
    assert not any(o["streamSettings"].get("security") == "reality" for o in proxies), "Reality в этот пул не идёт"
    assert auto["routing"]["balancers"][0]["fallbackTag"] == "direct"
    assert not any("130.49.143.41" in json.dumps(o) for o in proxies), "каскад через Москву в автовыборе не нужен"



def test_unbranded_links_overwrite_cached_support_and_site_with_empty_values(monkeypatch):
    monkeypatch.setattr(sub_gateway, "UNBRANDED_USERS", frozenset({"corp_fi_trial"}))
    monkeypatch.setattr(sub_gateway, "SUPPORT_URL", "https://t.me/unlock_support_bot")
    monkeypatch.setattr(sub_gateway, "PROFILE_WEB_PAGE_URL", "https://unlockproject.site")

    headers = sub_gateway._client_headers(_panel_token("corp_fi_trial"))

    assert headers["support-url"] == ""
    assert headers["profile-web-page-url"] == ""


def test_vk_relay_can_be_enabled_by_name_pattern(monkeypatch):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", True)
    monkeypatch.setattr(sub_gateway, "VK_RELAY_USERS", frozenset({"tg_*"}))
    monkeypatch.setattr(sub_gateway, "VK_RELAY_PBK", "pbk")
    monkeypatch.setattr(sub_gateway, "VK_RELAY_SID", "sid")
    monkeypatch.setattr(sub_gateway, "VK_RELAY_IDS", {"78.17.154.225.sslip.io": "uuid-pl"})
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (_vless("78.17.154.225.sslip.io"), None))

    links, _ = sub_gateway.resolve_links(_panel_token("tg_42"))

    names = [urllib.parse.unquote(l.rsplit("#", 1)[-1]) for l in links]
    assert any(n.endswith("✅ РУ сервисы · VK") for n in names), names
    assert not any("130.49.143.41" in l for l in links), "московский каскад заменён"


# --- 12.10.2026: «Авто-обход» сначала через мост (домашние провайдеры режут прямые адреса) ---

def _bridge(monkeypatch, users=frozenset({"tg_*"})):
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", True)
    monkeypatch.setattr(sub_gateway, "VK_RELAY_USERS", frozenset({"tg_*"}))
    monkeypatch.setattr(sub_gateway, "VK_RELAY_PBK", "pbk")
    monkeypatch.setattr(sub_gateway, "VK_RELAY_SID", "sid")
    monkeypatch.setattr(sub_gateway, "VK_RELAY_IDS", {
        "78.17.154.225.sslip.io": "uuid-pl", "178.17.58.232.sslip.io": "uuid-de", US_HOST: "uuid-us",
    })
    monkeypatch.setattr(sub_gateway, "AUTO_BRIDGE_USERS", users)
    monkeypatch.setattr(sub_gateway, "AUTO_HY2_URIS", (FI3_AUTO,))
    monkeypatch.setattr(sub_gateway, "COMPAT_USERS", frozenset())
    upstream = "\n".join([_vless(NL_HOST, 2053), _vless("78.17.154.225.sslip.io"), _vless(US_HOST, 2102)])
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))


def _auto_of(username):
    body, _, is_json = sub_gateway.build_auto_json(_panel_token(username), hysteria=True)
    assert is_json
    return json.loads(body)


def _proxies(config):
    return [o for o in config["outbounds"] if o["tag"].startswith("proxy-")]


def test_bridge_auto_uses_only_bridge_and_hysteria_with_a_direct_fallback(monkeypatch):
    _bridge(monkeypatch)
    for config in _auto_of("tg_42")[:2]:
        proxies = _proxies(config)
        ids = [o["settings"]["vnext"][0]["users"][0]["id"] for o in proxies if o["protocol"] == "vless"]
        assert ids == ["uuid-pl", "uuid-de"], "только мост, без прямых и без США через мост"
        assert [o["protocol"] for o in proxies][-1] == "hysteria"
        fallback = next(o for o in config["outbounds"] if o["tag"] == "fallback")
        assert fallback["settings"]["vnext"][0]["address"] not in ("212.233.122.241", "130.49.143.41")
        assert config["routing"]["balancers"][0]["fallbackTag"] == "fallback"
        assert not any(t.startswith("fallback") for t in config["observatory"]["subjectSelector"])


def test_bridge_auto_is_off_for_others_and_without_bridge_entries(monkeypatch):
    _bridge(monkeypatch, users=frozenset({"exp_ruvk_1"}))
    config = _auto_of("tg_42")[0]
    assert "fallbackTag" not in config["routing"]["balancers"][0]
    assert any(o["settings"].get("vnext", [{}])[0].get("address") == "107.189.22.160" for o in _proxies(config)), "обычный пул"
    _bridge(monkeypatch)
    monkeypatch.setattr(sub_gateway, "VK_RELAY_IDS", {})
    config = _auto_of("tg_42")[0]
    assert "fallbackTag" not in config["routing"]["balancers"][0], "моста нет в ссылке — обычный автовыбор"


def test_bridge_pool_never_applies_to_corporate_or_individual_links(monkeypatch):
    _bridge(monkeypatch, users=frozenset({"*", "tg_*", "corp_*", "ind_*"}))
    links = ["vless://uuid-pl@212.233.122.241:443?security=reality#a"]
    assert sub_gateway.bridge_auto_pool(links, "corp_unl_vpn") is None
    assert sub_gateway.bridge_auto_pool(links, "ind_de_2") is None
    assert sub_gateway.bridge_auto_pool(links, "tg_1")[0] == links


def test_bridge_fallback_skips_hosts_kept_out_of_auto(monkeypatch):
    _bridge(monkeypatch)
    links = ["vless://uuid-pl@212.233.122.241:443?security=reality#bridge",
             "vless://u@2.59.162.34:2101?security=reality#lt", "vless://u@78.17.154.225:2087?security=reality#pl"]
    assert sub_gateway.bridge_auto_pool(links, "tg_1")[1].endswith("#lt")
    assert sub_gateway.bridge_auto_pool(links, "tg_1", frozenset({"2.59.162.34"}))[1].endswith("#pl")


# --- 13.10.2026: ссылка «только Германия и Нидерланды, без российских серверов» ---

NLH1_HOST = "13.141.51.245.sslip.io"
DE_EXIT = "178.17.58.232.sslip.io"


def _foreign(monkeypatch, name="exp_denl_7d"):
    _bridge(monkeypatch)
    monkeypatch.setattr(sub_gateway, "AUTO_HY2_URIS", (
        f"hysteria2://unl_auto:pw2@{NLH1_HOST}:443?sni={NLH1_HOST}&insecure=0#nlh1", FI3_AUTO,
    ))
    monkeypatch.setattr(sub_gateway, "VK_RELAY_USERS", frozenset({"tg_*", "exp_*"}))
    monkeypatch.setattr(sub_gateway, "AUTO_BRIDGE_USERS", frozenset({"tg_*", "exp_*"}))
    monkeypatch.setattr(sub_gateway, "DE_VIA_UUID", "de-via-uuid")
    monkeypatch.setattr(sub_gateway, "DE_VIA_PBK", "pbk")
    monkeypatch.setattr(sub_gateway, "DE_VIA_EXIT_HOST", DE_EXIT)
    monkeypatch.setattr(sub_gateway, "FOREIGN_ONLY_USERS", {name: frozenset({NL_HOST, DE_EXIT, NLH1_HOST})})
    upstream = "\n".join([
        _vless(NL_HOST, 2053), f"vless://uuid@{NL_HOST}:2100?security=reality&type=xhttp#xhttp",
        _vless("78.17.154.225.sslip.io"), _vless(US_HOST, 2102),
    ])
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (upstream, None))


def test_foreign_only_link_lists_only_germany_and_netherlands(monkeypatch):
    _foreign(monkeypatch)
    links, _ = sub_gateway.resolve_links(_panel_token("exp_denl_7d"))
    endpoints = sorted(sub_gateway._uri_endpoint(l) for l in links)
    assert endpoints == [("107.189.22.160.sslip.io", 2053), ("78.17.154.225.sslip.io", 2120)], endpoints
    assert not any(h in "".join(links) for h in ("212.233.122.241", "130.49.143.41", "172.86.119.133")), "без РФ и чужих стран"


def test_foreign_only_auto_has_no_russian_paths_and_no_ru_mode(monkeypatch):
    _foreign(monkeypatch)
    configs = _auto_of("exp_denl_7d")
    remarks = [c["remarks"] for c in configs]
    assert not any("РУ" in r for r in remarks), remarks
    auto = configs[0]
    body = json.dumps(auto)
    assert "212.233.122.241" not in body and "130.49.143.41" not in body
    assert "89.125.86.10" not in body, "Hysteria2 Финляндии не нужна — только Нидерланды"
    addresses = sorted({(o["settings"].get("vnext") or [o["settings"]])[0].get("address") for o in _proxies(auto)})
    assert addresses == ["107.189.22.160", "13.141.51.245", "78.17.154.225"], addresses
    assert "fallbackTag" not in auto["routing"]["balancers"][0]


def test_other_links_are_unaffected_by_foreign_only(monkeypatch):
    _foreign(monkeypatch)
    links, _ = sub_gateway.resolve_links(_panel_token("exp_other_1"))
    assert any("212.233.122.241" in l for l in links), "обычная ссылка по-прежнему с мостом"


def _via_vk(monkeypatch):
    _foreign(monkeypatch)
    monkeypatch.setattr(sub_gateway, "FOREIGN_VIA_VK_USERS", frozenset({"exp_denl_7d"}))
    monkeypatch.setattr(sub_gateway, "VK_FULL_IDS", {DE_EXIT: "full-de-uuid", NL_HOST: "full-nl-uuid"})


def test_foreign_link_through_vk_shows_countries_but_connects_to_vk(monkeypatch):
    _via_vk(monkeypatch)
    links, _ = sub_gateway.resolve_links(_panel_token("exp_denl_7d"))
    names = sorted(urllib.parse.unquote(l.rsplit("#", 1)[-1]) for l in links)
    assert names == ["🇩🇪 Германия", "🇳🇱 Нидерланды"], names
    assert {sub_gateway._uri_host(l) for l in links} == {"212.233.122.241.sslip.io"}
    assert sorted(sub_gateway._uri_userinfo(l) for l in links) == ["full-de-uuid", "full-nl-uuid"]
    assert not any("РУ" in n for n in names)


def test_foreign_link_through_vk_auto_uses_both_bridge_keys_and_direct_fallback(monkeypatch):
    _via_vk(monkeypatch)
    configs = _auto_of("exp_denl_7d")
    assert [c["remarks"] for c in configs][1:] == ["🇩🇪 Германия", "🇳🇱 Нидерланды"] or len(configs) == 3
    auto = configs[0]
    ids = sorted(o["settings"]["vnext"][0]["users"][0]["id"] for o in _proxies(auto))
    assert ids == ["full-de-uuid", "full-nl-uuid"], "оба ключа моста, без Hysteria2 мимо моста"
    fallback = next(o for o in auto["outbounds"] if o["tag"] == "fallback")
    assert fallback["settings"]["vnext"][0]["address"] == "107.189.22.160"
    assert auto["routing"]["balancers"][0]["fallbackTag"] == "fallback"


def test_foreign_link_falls_back_to_direct_entries_when_vk_is_dead(monkeypatch):
    _via_vk(monkeypatch)
    monkeypatch.setattr(sub_gateway, "_probed_dead_hosts", lambda: {"212.233.122.241.sslip.io"})
    links, _ = sub_gateway.resolve_links(_panel_token("exp_denl_7d"))
    assert links and not any("212.233.122.241" in l for l in links)


# --- 14.10.2026: страница выбора приложения для ссылок Etalon (Happ, INCY, V2Box) ---

SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"


def _picker_env(monkeypatch):
    monkeypatch.setattr(sub_gateway, "PICKER_USERS", frozenset({"corp_mrt_*"}))
    monkeypatch.setattr(sub_gateway, "PICKER_ACCENTS", {"corp_mrt_*": "#D4B06A"})
    monkeypatch.setattr(sub_gateway, "SUB_TITLES", {"corp_mrt_*": "Etalon VPN"})
    monkeypatch.setattr(sub_gateway, "SUB_BASES", {"corp_mrt_*": "https://m.example.test"})


def test_browser_gets_the_app_picker_for_picker_links(monkeypatch):
    _picker_env(monkeypatch)
    token = _panel_token(MRT)
    handler = _FakeHandler(f"/sub/{token}", {"User-Agent": SAFARI, "Host": "gw.example"})
    handler.do_GET()
    page = handler.sent["body"].decode()
    sub = f"https://m.example.test/sub/{token}"
    assert handler.sent["code"] == 200 and handler.sent["ctype"].startswith("text/html")
    assert f'href="happ://add/{sub}"' in page and f'href="incy://add/{sub}"' in page
    v2box = "v2box://install-sub?url=" + urllib.parse.quote(sub, safe="") + "&amp;name=Etalon%20VPN"
    assert f'href="{v2box}"' in page
    assert "Etalon VPN" in page and "#D4B06A" in page and "unlock" not in page.lower()
    assert page.count("Скачать ") == 3 and "Скопировать ссылку" in page


def test_picker_keeps_the_flavor_in_the_imported_link(monkeypatch):
    _picker_env(monkeypatch)
    token = _panel_token(MRT)
    handler = _FakeHandler(f"/sub/{token}/auto", {"User-Agent": SAFARI})
    handler.do_GET()
    assert f"happ://add/https://m.example.test/sub/{token}/auto" in handler.sent["body"].decode()


def test_other_links_still_bounce_the_browser_to_happ(monkeypatch):
    _picker_env(monkeypatch)
    redirects = []
    handler = _FakeHandler(f"/sub/{_panel_token('tg_1')}", {"User-Agent": SAFARI, "Host": "gw.example"})
    handler.send_response = lambda code: redirects.append(code)
    handler.send_header = lambda name, value: redirects.append((name, value))
    handler.end_headers = lambda: None
    handler.do_GET()
    assert redirects[0] == 302 and any(h == "Location" and "/happ/" in v for h, v in redirects[1:])


def test_picker_page_picks_readable_text_on_the_accent():
    assert sub_gateway._ink_for("#D4B06A") == "#14171f" and sub_gateway._ink_for("#0F1A33") == "#ffffff"


# --- 14.10.2026: своё название «Авто» для ссылок Etalon («Авто-выбор» по просьбе платёжного провайдера) ---

def test_auto_entry_title_can_be_set_per_account(monkeypatch):
    monkeypatch.setattr(sub_gateway, "AUTO_TITLES", {"corp_mrt_*": "⚡️ Авто-выбор"})
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (_vless(NL_HOST) + "\n" + _vless(US_HOST, 2102), None))
    mrt, _, _ = sub_gateway.build_auto_json(_panel_token(MRT))
    ours, _, _ = sub_gateway.build_auto_json(_panel_token("tg_1"))
    assert json.loads(mrt)[0]["remarks"] == "⚡️ Авто-выбор"
    assert json.loads(ours)[0]["remarks"] == "⚡️ Авто-обход", "наши подписки — как раньше"
