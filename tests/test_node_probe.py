import urllib.parse

import pytest

from services import node_probe

US = "🇺🇸 США"
PL = "🇵🇱 Польша"


def _uri(scheme: str, host: str, port: int, remark: str) -> str:
    return f"{scheme}://cred@{host}:{port}?type=tcp#{urllib.parse.quote(remark)}"


SUB = "\n".join(
    [
        _uri("vless", "us.example", 443, US),
        _uri("hysteria2", "us.example", 443, f"{US} · Hysteria2"),
        _uri("vless", "pl.example", 2087, PL),
        _uri("trojan", "pl.example", 8444, f"{PL} · Trojan"),
        _uri("hysteria2", "pl.example", 443, f"{PL} · Hysteria2"),
    ]
)


@pytest.mark.unit
def test_parse_location_endpoints_groups_by_location_skips_udp():
    targets = node_probe.parse_location_endpoints(SUB)
    # hysteria2 (UDP) is skipped; vless/trojan grouped under their location
    assert targets[("🇺🇸", "США")] == [("us.example", 443)]
    assert set(targets[("🇵🇱", "Польша")]) == {("pl.example", 2087), ("pl.example", 8444)}
    assert all("Hysteria2" not in name for _, name in targets)


@pytest.mark.unit
def test_location_key_drops_protocol_suffix():
    assert node_probe._location_key("🇵🇱 Польша · Trojan") == ("🇵🇱", "Польша")
    assert node_probe._location_key("🇺🇸 США") == ("🇺🇸", "США")


@pytest.mark.unit
def test_endpoint_parses_host_and_port():
    assert node_probe._endpoint("vless://x@h.example:2087?type=tcp#r") == ("h.example", 2087)
    assert node_probe._endpoint("trojan://x@h.example?security=tls") == ("h.example", 443)
    assert node_probe._endpoint("garbage") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_probe_subscription_reports_per_location_health(monkeypatch):
    monkeypatch.setattr(node_probe, "_fetch_decoded", lambda url: SUB)

    async def fake_tcp(host, port):
        return host != "us.example"  # US down, PL up

    monkeypatch.setattr(node_probe, "_tcp_ok", fake_tcp)

    result = {(h.flag, h.name): h.reachable for h in await node_probe.probe_subscription("https://sub/x")}
    assert result[("🇺🇸", "США")] is False
    assert result[("🇵🇱", "Польша")] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_probe_subscription_empty_on_fetch_error(monkeypatch):
    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(node_probe, "_fetch_decoded", boom)
    assert await node_probe.probe_subscription("https://sub/x") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_probe_subscription_empty_for_blank_url():
    assert await node_probe.probe_subscription("") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_location_reachable_true_if_any_endpoint_up(monkeypatch):
    async def one_up(host, port):
        return port == 8444

    monkeypatch.setattr(node_probe, "_tcp_ok", one_up)
    assert await node_probe._location_reachable([("h", 2087), ("h", 8444)]) is True
    assert await node_probe._location_reachable([("h", 2087)]) is False
