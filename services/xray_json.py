"""Build Xray-JSON subscription entries from proxy URIs.

Some clients (Happ, v2rayN, Streisand) accept a subscription whose body is a
JSON array of full xray-core configs instead of a base64 list of `scheme://`
URIs — each array element is a complete config the client runs 1:1. That lets
us ship an **«⚡️ Авто-обход»** entry: a single config with an observatory that
pings every server and a routing balancer (`leastPing`) that sends traffic
through the fastest live one and re-routes on the fly when it degrades — the
"tap once, always works" server the non-technical user wants.

Only xray-core protocols (VLESS, Trojan) go into these configs; Hysteria2 runs
on a different core in Happ and cannot live inside an xray balancer, so it is
skipped here (the plain base64 subscription still carries it).

Pure functions, stdlib only — mirrors the gateway it feeds.
"""
from __future__ import annotations

import urllib.parse

# Standard local inbounds an xray-json client bridges its TUN to (socks + http).
# Ports per the XTLS JSON-subscription convention (10808/10809).
_INBOUNDS = [
    {
        "tag": "socks-in",
        "listen": "127.0.0.1",
        "port": 10808,
        "protocol": "socks",
        "settings": {"udp": True, "auth": "noauth"},
        "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
    },
    {
        "tag": "http-in",
        "listen": "127.0.0.1",
        "port": 10809,
        "protocol": "http",
    },
]

_PROBE_URL = "https://www.gstatic.com/generate_204"
_PROBE_INTERVAL = "3m"

AUTO_REMARKS = "⚡️ Авто-обход"


def _tail_outbounds() -> list[dict]:
    return [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
    ]


def _parse_uri(uri: str) -> tuple[str, str, str, int, dict, str] | None:
    """Split a proxy URI into (scheme, userinfo, host, port, query, remark).

    Returns None when the URI isn't a parseable `scheme://userinfo@host:port`.
    """
    if "://" not in uri:
        return None
    scheme, rest = uri.split("://", 1)
    if "@" not in rest:
        return None
    userinfo, after_at = rest.split("@", 1)
    hostportq, _, fragment = after_at.partition("#")
    hostport, _, query_str = hostportq.partition("?")
    host = hostport.split(":", 1)[0]
    if not host:
        return None
    port = 443
    if ":" in hostport:
        try:
            port = int(hostport.rsplit(":", 1)[1])
        except ValueError:
            return None
    query = {k: v[0] for k, v in urllib.parse.parse_qs(query_str, keep_blank_values=True).items()}
    remark = urllib.parse.unquote(fragment) if fragment else host
    return scheme.lower(), userinfo, host, port, query, remark


def _stream_settings(query: dict) -> dict:
    network = query.get("type", "tcp") or "tcp"
    security = query.get("security", "none") or "none"
    stream: dict = {"network": network, "security": security}
    sni = query.get("sni") or query.get("host") or ""
    fingerprint = query.get("fp", "")
    if security == "reality":
        reality = {
            "serverName": sni,
            "publicKey": query.get("pbk", ""),
            "shortId": query.get("sid", ""),
            "spiderX": query.get("spx", ""),
        }
        if fingerprint:
            reality["fingerprint"] = fingerprint
        stream["realitySettings"] = reality
    elif security == "tls":
        tls: dict = {"serverName": sni}
        if fingerprint:
            tls["fingerprint"] = fingerprint
        stream["tlsSettings"] = tls
    return stream


def build_outbound(uri: str, tag: str) -> dict | None:
    """Map one VLESS/Trojan URI to an xray outbound. None for anything else."""
    parsed = _parse_uri(uri)
    if parsed is None:
        return None
    scheme, userinfo, host, port, query, _ = parsed

    if scheme == "vless":
        user: dict = {"id": userinfo, "encryption": query.get("encryption", "none") or "none"}
        flow = query.get("flow")
        if flow:
            user["flow"] = flow
        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
            "streamSettings": _stream_settings(query),
        }
    if scheme == "trojan":
        return {
            "tag": tag,
            "protocol": "trojan",
            "settings": {"servers": [{"address": host, "port": port, "password": userinfo}]},
            "streamSettings": _stream_settings(query),
        }
    return None


def _remark(uri: str, fallback: str) -> str:
    parsed = _parse_uri(uri)
    return parsed[5] if parsed else fallback


def build_server_config(uri: str, tag_index: int) -> dict | None:
    """A standalone single-server xray config (so the user can still pick one)."""
    outbound = build_outbound(uri, "proxy")
    if outbound is None:
        return None
    return {
        "remarks": _remark(uri, f"Сервер {tag_index + 1}"),
        "log": {"loglevel": "warning"},
        "inbounds": _INBOUNDS,
        "outbounds": [outbound, *_tail_outbounds()],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [{"type": "field", "network": "tcp,udp", "outboundTag": "proxy"}],
        },
    }


def build_balancer_config(uris: list[str], remarks: str = AUTO_REMARKS) -> dict | None:
    """A single config that load-balances (leastPing) across all servers.

    xray's observatory pings each `proxy-*` outbound; the balancer routes every
    connection through the lowest-latency healthy one and re-picks when it
    degrades — automatic bypass with no user action. None when no xray-core
    outbound could be built.
    """
    outbounds: list[dict] = []
    for uri in uris:
        outbound = build_outbound(uri, f"proxy-{len(outbounds)}")
        if outbound is not None:
            outbounds.append(outbound)
    if not outbounds:
        return None
    return {
        "remarks": remarks,
        "log": {"loglevel": "warning"},
        "inbounds": _INBOUNDS,
        "outbounds": [*outbounds, *_tail_outbounds()],
        "routing": {
            "domainStrategy": "AsIs",
            "balancers": [
                {"tag": "auto", "selector": ["proxy-"], "strategy": {"type": "leastPing"}}
            ],
            "rules": [{"type": "field", "network": "tcp,udp", "balancerTag": "auto"}],
        },
        "observatory": {
            "subjectSelector": ["proxy-"],
            "probeUrl": _PROBE_URL,
            "probeInterval": _PROBE_INTERVAL,
            "enableConcurrency": True,
        },
    }


def build_json_subscription(links: list[str]) -> list[dict]:
    """Full JSON-array body: the balancer first, then each server on its own.

    Empty when no xray-core-compatible server is present (caller then falls
    back to the plain base64 subscription).
    """
    balancer = build_balancer_config(links)
    if balancer is None:
        return []
    configs = [balancer]
    for index, uri in enumerate(links):
        server = build_server_config(uri, index)
        if server is not None:
            configs.append(server)
    return configs
