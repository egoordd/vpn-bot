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

import json
import os
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

# Plain http:// on purpose: the observatory measures a server's latency by
# fetching this, and an https:// probe adds a full TLS handshake to gstatic
# *inside* the tunnel to every measurement. That inflates each reading by a
# round-trip or three on a throttled RU link and distorts which server
# leastPing considers fastest. 204-generators are served over HTTP for exactly
# this reason.
_PROBE_URL = "http://www.gstatic.com/generate_204"
# Failover speed: this interval *is* the outage a user sits through, because a
# balancer can only route around a server once a fresh probe has judged it. The
# old 3m let a node black-hole traffic for three minutes — "connected but
# nothing loads", switch by hand.
#
# 15s was the first correction and overshot: a probe round dials *every* proxy,
# so with a location per entry that is a burst of tunnel setups four times a
# minute, running forever in the background. On a phone that reads as an app
# that never idles, which is what battery optimisers kill — and a killed app is
# itself reported as "the VPN disconnects on its own". 60s still detects a dead
# node three times faster than the original while leaving the client mostly
# quiet.
_PROBE_INTERVAL = "60s"
_PROBE_TIMEOUT = "4s"
# Samples kept per server: the strategy judges on the recent window, so a node
# that degrades (rather than dies outright) is demoted after a couple of bad
# samples instead of staying selected on one stale good reading.
_PROBE_SAMPLING = 3
# A server slower than this is treated as unusable, which is what makes
# "switches when a server just gets slow" work at all — pure latency ranking
# keeps picking the least-bad node even when every reading is terrible.
_MAX_RTT = "4s"

# leastPing ranks purely on measured latency, which is exactly what a user
# feels: a node that merely gets slow sinks in the ranking on the next probe
# and stops being picked, so short _PROBE_INTERVAL covers both "died" and
# "долго грузит". leastLoad optimises for *stability* instead and measurably
# picked worse servers here — benchmarked from a real RU line 2026-07-28,
# leastPing 295/421ms via Frankfurt vs leastLoad 465/616ms via Amsterdam — so
# it stays available (BALANCER_STRATEGY=leastload) but is not the default.
BALANCER_STRATEGY = os.environ.get("BALANCER_STRATEGY", "leastping").strip().lower()

AUTO_REMARKS = "⚡️ Авто-обход"

# Resolver for routing decisions (matching a destination against geoip:ru).
# geoip:ru needs the destination IP, so IPOnDemand resolves every domain here
# before it can route.
#
# These MUST stay remote. The device's own resolver is the RU ISP's, and it
# refuses to answer for blocked domains at all — measured 2026-07-29 from an
# MTS line: tiktok.com, instagram.com, cdninstagram.com and tiktokcdn.com all
# return an empty answer, while 1.1.1.1 resolves every one. Putting `localhost`
# first (briefly done on 2026-07-28) therefore left those apps unable to look
# up fresh CDN hosts, so they fell back to cached content — "Instagram shows
# old posts, TikTok doesn't work". Resolving through the tunnel also keeps the
# ISP from seeing which sites are being looked up.
_DNS = {"servers": ["localhost"]}

# Russian destinations that must leave the device directly, matched by NAME so
# no lookup is needed to decide. The regexps cover the national zones in one
# line each; the rest are the RU services that live outside them.
_RU_DIRECT_DOMAINS = [
    "regexp:\\.ru$",
    "regexp:\\.su$",
    "regexp:\\.xn--p1ai$",  # .рф
    "domain:vk.com",
    "domain:vk.me",
    "domain:userapi.com",
    "domain:mycdn.me",
    "domain:yandex.net",
    "domain:yandex.com",
    "domain:ozon.com",
    "domain:wildberries.com",
    "domain:gosuslugi.gov",
]

# Domains that must never take the geoip:ru direct path, whatever their address
# resolves to.
#
# This is the sharp edge of the RU-split feature. Sending `geoip:ru` straight
# out of the device is right for banks and gosuslugi, but every one of these
# platforms is blocked or throttled in RU *and* keeps CDN capacity inside the
# country — YouTube most of all, whose Google Global Cache nodes sit in Russian
# ISPs. A lookup landing on one of those returns a Russian address, geoip:ru
# then routes it out of the device, and the request arrives at an edge that is
# frozen (TikTok has served no new RU content since 2022), filtered, or
# deliberately throttled. The user sees stale feeds and crawling video rather
# than an error — the VPN looks connected and broken at the same time, which is
# exactly what was reported and what competitors without RU-split don't suffer.
#
# Matching on the domain, ahead of every IP rule, decides before an address is
# even known, so no CDN placement can undo it.
_FORCE_PROXY_DOMAINS = [
    # TikTok / ByteDance
    "domain:tiktok.com",
    "domain:tiktokcdn.com",
    "domain:tiktokcdn-us.com",
    "domain:tiktokcdn-eu.com",
    "domain:tiktokcdn-in.com",
    "domain:tiktokv.com",
    "domain:tiktokv.us",
    "domain:ttlivecdn.com",
    "domain:ttwstatic.com",
    "domain:byteoversea.com",
    "domain:byteicdn.com",
    "domain:bytedance.com",
    "domain:bytedapm.com",
    "domain:ibytedtos.com",
    "domain:ipstatp.com",
    "domain:sgpstatp.com",
    "domain:snssdk.com",
    "domain:isnssdk.com",
    "domain:muscdn.com",
    "domain:musical.ly",
    "domain:capcut.com",
    # Meta
    "domain:instagram.com",
    "domain:cdninstagram.com",
    "domain:fbcdn.net",
    "domain:facebook.com",
    "domain:fb.com",
    "domain:threads.net",
    "domain:whatsapp.com",
    "domain:whatsapp.net",
    # YouTube / Google video — googlevideo.com is the throttled one, and its
    # cache nodes are physically inside RU networks.
    "domain:youtube.com",
    "domain:youtu.be",
    "domain:googlevideo.com",
    "domain:ytimg.com",
    "domain:ggpht.com",
    "domain:youtubei.googleapis.com",
    # Other blocked platforms with RU-facing infrastructure
    "domain:twitter.com",
    "domain:x.com",
    "domain:twimg.com",
]


def _tail_outbounds() -> list[dict]:
    return [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
    ]


# Send Russian destinations straight out the device (real local IP) instead of
# tunnelling them to a foreign exit and back: RU banks / gosuslugi / apps then
# see a Russian IP and work, and RU traffic — most of a user's day — takes zero
# VPN detour, which is the biggest lever on felt latency.
#
# Everything is decided by NAME, and that is the whole point. Deciding by
# address means resolving first, and every way of doing that has now broken a
# client in production: resolving through the tunnel wedges the app when the
# chosen node dies (it cannot even fail over, because failing over needs a
# lookup), while routing port 53 out of the tunnel loops on a phone, where the
# VPN owns the system resolver — the lookup leaves, comes straight back in, and
# nothing loads at all. With `AsIs` no lookup happens for routing, so neither
# failure can occur. Names go to the exit and are resolved there.
def _split_routing(final_rule: dict) -> dict:
    # Whatever `final_rule` sends traffic to (a single proxy outbound, or the
    # balancer) is where the pinned domains must go too.
    destination = {
        key: value for key, value in final_rule.items() if key in ("outboundTag", "balancerTag")
    }
    return {
        "domainStrategy": "AsIs",
        "rules": [
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
            # Blocked platforms first: they must reach the tunnel even though
            # some of their CDN sits on Russian addresses.
            {"type": "field", "domain": _FORCE_PROXY_DOMAINS, **destination},
            {"type": "field", "domain": _RU_DIRECT_DOMAINS, "outboundTag": "direct"},
            # Catches apps that connect to a Russian address with no name at all.
            {"type": "field", "ip": ["geoip:ru"], "outboundTag": "direct"},
            final_rule,
        ],
    }


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


# Client-side TCP keepalive: a carrier CGNAT drops an idle tunnel mapping at
# ~15-30min, leaving the connection half-open («подключён, но не грузит»).
# Probing every ~25s (after 30s idle) keeps the mapping fresh from the outbound
# direction — the server inbounds carry the same option for the return path.
_KEEPALIVE_SOCKOPT = {"tcpKeepAliveIdle": 30, "tcpKeepAliveInterval": 25}


def _xhttp_settings(query: dict) -> dict:
    """Transport block for an XHTTP link.

    XHTTP carries the tunnel inside ordinary HTTP requests, which survives DPI
    that recognises and kills a raw TLS-shaped stream — the transport a client
    falls back to when Reality-over-TCP stops connecting. Without this block the
    JSON config would name the network but omit its path, and the connection
    would fail; the panel puts the tuning knobs in `extra` as JSON.
    """
    settings: dict = {"path": query.get("path", "/"), "mode": query.get("mode", "auto")}
    host = query.get("host", "")
    if host:
        settings["host"] = host
    extra = query.get("extra", "")
    if extra:
        try:
            parsed = json.loads(extra)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            settings["extra"] = parsed
    return settings


def _stream_settings(query: dict) -> dict:
    network = query.get("type", "tcp") or "tcp"
    security = query.get("security", "none") or "none"
    stream: dict = {"network": network, "security": security, "sockopt": dict(_KEEPALIVE_SOCKOPT)}
    if network == "xhttp":
        stream["xhttpSettings"] = _xhttp_settings(query)
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
        "dns": _DNS,
        "inbounds": _INBOUNDS,
        "outbounds": [outbound, *_tail_outbounds()],
        "routing": _split_routing(
            {"type": "field", "network": "tcp,udp", "outboundTag": "proxy"}
        ),
    }


def _health_check(strategy: str) -> tuple[dict, dict]:
    """(balancer strategy, health-probe block) for the configured strategy.

    leastLoad needs `burstObservatory` (rolling samples + a timeout), leastPing
    needs the plain `observatory`; the two are not interchangeable, so the pair
    is built together to keep them consistent.
    """
    if strategy != "leastload":
        return (
            {"type": "leastPing"},
            {
                "observatory": {
                    "subjectSelector": ["proxy-"],
                    "probeUrl": _PROBE_URL,
                    "probeInterval": _PROBE_INTERVAL,
                    "enableConcurrency": True,
                }
            },
        )
    return (
        # `expected: 2` keeps a second healthy server in play instead of pinning
        # every connection to a single "best" one, so one node degrading never
        # takes the whole session down with it.
        {"type": "leastLoad", "settings": {"expected": 2, "maxRTT": _MAX_RTT, "tolerance": 0.3}},
        {
            "burstObservatory": {
                "subjectSelector": ["proxy-"],
                "pingConfig": {
                    "destination": _PROBE_URL,
                    "interval": _PROBE_INTERVAL,
                    "timeout": _PROBE_TIMEOUT,
                    "sampling": _PROBE_SAMPLING,
                },
            }
        },
    )


def build_balancer_config(uris: list[str], remarks: str = AUTO_REMARKS) -> dict | None:
    """A single config that balances across every server, healthiest first.

    A health prober samples each `proxy-*` outbound continuously; the balancer
    routes each connection through a server that is currently fast, and demotes
    one that dies *or merely gets slow* (see _MAX_RTT) without the user
    touching anything. None when no xray-core outbound could be built.
    """
    outbounds: list[dict] = []
    for uri in uris:
        outbound = build_outbound(uri, f"proxy-{len(outbounds)}")
        if outbound is not None:
            outbounds.append(outbound)
    if not outbounds:
        return None
    strategy, prober = _health_check(BALANCER_STRATEGY)
    return {
        "remarks": remarks,
        "log": {"loglevel": "warning"},
        "dns": _DNS,
        "inbounds": _INBOUNDS,
        "outbounds": [*outbounds, *_tail_outbounds()],
        "routing": {
            **_split_routing({"type": "field", "network": "tcp,udp", "balancerTag": "auto"}),
            "balancers": [{"tag": "auto", "selector": ["proxy-"], "strategy": strategy}],
        },
        **prober,
    }


def build_json_subscription(links: list[str]) -> list[dict]:
    """Full JSON-array body: the balancer first, then each server on its own.

    Objects only: mixing raw URI strings into the array broke Happ's import
    outright («there are no server links», verified live 2026-07-16), so
    non-xray protocols (Hysteria2 — separate core) simply cannot ride in this
    format and are left to the base64 flavor other clients receive.

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
