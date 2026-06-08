import json

import pytest

from services.client_profiles import (
    Hysteria2Endpoint,
    ProfileError,
    ShadowsocksEndpoint,
    VlessRealityEndpoint,
    build_happ_xray_profile,
    dumps_happ_xray_profile,
    endpoint_from_dict,
    endpoints_from_dicts,
)


def _reality() -> VlessRealityEndpoint:
    return VlessRealityEndpoint(
        tag="nl reality",
        address="node.example.com",
        port=443,
        uuid="0d5fd88e-faa0-4055-bd90-4086fe20f050",
        public_key="public-key",
        server_name="node.example.com",
        short_id="5e8b1d4c9a7f2e30",
    )


def _hysteria() -> Hysteria2Endpoint:
    return Hysteria2Endpoint(
        tag="hy2",
        address="node.example.com",
        port=8443,
        auth="secret",
        server_name="node.example.com",
        pinned_peer_cert_sha256="a" * 64,
    )


@pytest.mark.unit
def test_build_happ_xray_profile_with_auto_fallback():
    profile = build_happ_xray_profile([_reality(), _hysteria()], remarks="Test VPN")

    assert profile["remarks"] == "Test VPN"
    assert profile["dns"]["queryStrategy"] == "UseIPv4"
    assert profile["inbounds"][0]["protocol"] == "socks"
    assert profile["inbounds"][0]["sniffing"]["destOverride"] == ["http", "tls", "quic"]

    outbounds = {outbound["tag"]: outbound for outbound in profile["outbounds"]}
    assert set(outbounds) == {"proxy-nl-reality", "proxy-hy2", "direct", "block"}
    assert outbounds["proxy-nl-reality"]["protocol"] == "vless"
    assert outbounds["proxy-nl-reality"]["streamSettings"]["realitySettings"]["fingerprint"] == "firefox"
    assert outbounds["proxy-hy2"]["protocol"] == "hysteria"
    assert outbounds["proxy-hy2"]["settings"]["version"] == 2
    assert outbounds["proxy-hy2"]["streamSettings"]["tlsSettings"]["pinnedPeerCertSha256"] == ["a" * 64]

    assert profile["burstObservatory"]["subjectSelector"] == ["proxy-"]
    assert profile["routing"]["balancers"] == [
        {
            "tag": "auto",
            "selector": ["proxy-"],
            "fallbackTag": "proxy-nl-reality",
            "strategy": {"type": "leastPing"},
        }
    ]
    assert profile["routing"]["rules"][-1] == {
        "type": "field",
        "network": "tcp,udp",
        "balancerTag": "auto",
    }


@pytest.mark.unit
def test_build_happ_xray_profile_single_endpoint_uses_direct_outbound_tag():
    profile = build_happ_xray_profile([_hysteria()])

    assert "burstObservatory" not in profile
    assert "balancers" not in profile["routing"]
    assert profile["routing"]["rules"][-1] == {
        "type": "field",
        "network": "tcp,udp",
        "outboundTag": "proxy-hy2",
    }


@pytest.mark.unit
def test_build_happ_xray_profile_can_disable_bittorrent_block():
    profile = build_happ_xray_profile([_reality()], block_bittorrent=False)

    assert all(rule.get("protocol") != ["bittorrent"] for rule in profile["routing"]["rules"])


@pytest.mark.unit
def test_build_happ_xray_profile_rejects_duplicate_tags():
    with pytest.raises(ProfileError, match="duplicate endpoint tag"):
        build_happ_xray_profile([_hysteria(), _hysteria()])


@pytest.mark.unit
def test_build_happ_xray_profile_rejects_empty_endpoints():
    with pytest.raises(ProfileError, match="at least one endpoint"):
        build_happ_xray_profile([])


@pytest.mark.unit
def test_build_happ_xray_profile_rejects_bad_port():
    endpoint = ShadowsocksEndpoint(
        tag="ss",
        address="node.example.com",
        port=70000,
        password="secret",
    )

    with pytest.raises(ProfileError, match="port"):
        build_happ_xray_profile([endpoint])


@pytest.mark.unit
def test_endpoint_from_dict_accepts_live_probe_aliases():
    endpoints = endpoints_from_dicts(
        [
            {
                "protocol": "vless-reality",
                "tag": "reality",
                "server": "node.example.com",
                "server_port": 443,
                "id": "uuid",
                "pbk": "public-key",
                "sni": "node.example.com",
                "sid": "short-id",
                "fp": "firefox",
            },
            {
                "protocol": "hy2",
                "tag": "hy2",
                "server": "node.example.com",
                "server_port": 8443,
                "password": "secret",
                "sni": "node.example.com",
                "pinSHA256": "b" * 64,
            },
        ]
    )

    profile = build_happ_xray_profile(endpoints)
    outbounds = {outbound["tag"]: outbound for outbound in profile["outbounds"]}
    assert outbounds["proxy-reality"]["protocol"] == "vless"
    assert outbounds["proxy-reality"]["streamSettings"]["realitySettings"]["fingerprint"] == "firefox"
    assert outbounds["proxy-hy2"]["streamSettings"]["tlsSettings"]["pinnedPeerCertSha256"] == ["b" * 64]


@pytest.mark.unit
def test_endpoint_from_dict_rejects_unknown_protocol():
    with pytest.raises(ProfileError, match="unsupported endpoint protocol"):
        endpoint_from_dict({"protocol": "openvpn"})


@pytest.mark.unit
def test_dumps_happ_xray_profile_outputs_json():
    profile = build_happ_xray_profile([_reality()])

    pretty = dumps_happ_xray_profile(profile)
    compact = dumps_happ_xray_profile(profile, pretty=False)

    assert pretty.endswith("\n")
    assert json.loads(pretty)["remarks"] == "UnLock VPN"
    assert json.loads(compact)["outbounds"][0]["tag"] == "proxy-nl-reality"
    assert "\n" not in compact
