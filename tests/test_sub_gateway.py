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
