from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol


class ProfileError(ValueError):
    pass


class XrayEndpoint(Protocol):
    tag: str

    def to_xray_outbound(self, tag: str) -> dict[str, Any]:
        pass


DEFAULT_DIRECT_DOMAINS = (
    "domain:mtalk.google.com",
    "domain:push.apple.com",
    "domain:api.push.apple.com",
    "domain:push-apple.com.akadns.net",
    "domain:courier.push.apple.com",
    "domain:yandex.com",
    "domain:yandex.net",
    "domain:mail.ru",
    "domain:vk.com",
    "domain:vkusvill.ru",
    "domain:ozon.ru",
    "domain:wildberries.ru",
    "domain:sberbank.ru",
    "domain:tinkoff.ru",
    "domain:gosuslugi.ru",
    "domain:nalog.gov.ru",
    "domain:mos.ru",
    "domain:2gis.com",
    "domain:2gis.ru",
)

DEFAULT_DIRECT_IPS = (
    "17.0.0.0/8",
    "geoip:ru",
    "geoip:private",
)


def _require(value: str | None, field: str) -> str:
    if value is None or not str(value).strip():
        raise ProfileError(f"{field} is required")
    return str(value).strip()


def _validate_port(port: int, field: str = "port") -> int:
    if not 1 <= int(port) <= 65535:
        raise ProfileError(f"{field} must be between 1 and 65535")
    return int(port)


def _clean_tag(value: str) -> str:
    tag = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    if not tag:
        raise ProfileError("endpoint tag is required")
    return tag


def _proxy_tag(value: str) -> str:
    tag = _clean_tag(value)
    return tag if tag.startswith("proxy-") else f"proxy-{tag}"


@dataclass(frozen=True)
class VlessRealityEndpoint:
    tag: str
    address: str
    port: int
    uuid: str
    public_key: str
    server_name: str
    short_id: str
    flow: str = ""
    fingerprint: str = "firefox"
    spider_x: str = ""

    def to_xray_outbound(self, tag: str) -> dict[str, Any]:
        user = {
            "id": _require(self.uuid, "vless.uuid"),
            "encryption": "none",
        }
        if self.flow:
            user["flow"] = self.flow

        return {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": _require(self.address, "vless.address"),
                        "port": _validate_port(self.port, "vless.port"),
                        "users": [user],
                    }
                ]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "tcpSettings": {},
                "realitySettings": {
                    "serverName": _require(self.server_name, "vless.server_name"),
                    "fingerprint": self.fingerprint,
                    "publicKey": _require(self.public_key, "vless.public_key"),
                    "shortId": _require(self.short_id, "vless.short_id"),
                    "spiderX": self.spider_x,
                },
            },
            "tag": tag,
        }


@dataclass(frozen=True)
class Hysteria2Endpoint:
    tag: str
    address: str
    port: int
    auth: str
    server_name: str
    fingerprint: str = "chrome"
    alpn: tuple[str, ...] = ("h3",)
    congestion: str = "bbr"
    pinned_peer_cert_sha256: str | None = None

    def to_xray_outbound(self, tag: str) -> dict[str, Any]:
        tls_settings: dict[str, Any] = {
            "serverName": _require(self.server_name, "hysteria2.server_name"),
            "fingerprint": self.fingerprint,
            "alpn": list(self.alpn),
        }
        if self.pinned_peer_cert_sha256:
            tls_settings["pinnedPeerCertSha256"] = [self.pinned_peer_cert_sha256]

        return {
            "protocol": "hysteria",
            "settings": {
                "address": _require(self.address, "hysteria2.address"),
                "port": _validate_port(self.port, "hysteria2.port"),
                "version": 2,
            },
            "streamSettings": {
                "network": "hysteria",
                "security": "tls",
                "hysteriaSettings": {
                    "auth": _require(self.auth, "hysteria2.auth"),
                    "version": 2,
                },
                "finalmask": {
                    "quicParams": {
                        "congestion": self.congestion,
                        "debug": False,
                    }
                },
                "tlsSettings": tls_settings,
            },
            "tag": tag,
        }


@dataclass(frozen=True)
class ShadowsocksEndpoint:
    tag: str
    address: str
    port: int
    password: str
    method: str = "chacha20-ietf-poly1305"

    def to_xray_outbound(self, tag: str) -> dict[str, Any]:
        return {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [
                    {
                        "address": _require(self.address, "shadowsocks.address"),
                        "port": _validate_port(self.port, "shadowsocks.port"),
                        "method": _require(self.method, "shadowsocks.method"),
                        "password": _require(self.password, "shadowsocks.password"),
                    }
                ]
            },
            "tag": tag,
        }


@dataclass(frozen=True)
class TrojanTlsEndpoint:
    tag: str
    address: str
    port: int
    password: str
    server_name: str
    fingerprint: str = "chrome"
    alpn: tuple[str, ...] = ("http/1.1",)

    def to_xray_outbound(self, tag: str) -> dict[str, Any]:
        return {
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": _require(self.address, "trojan.address"),
                        "port": _validate_port(self.port, "trojan.port"),
                        "password": _require(self.password, "trojan.password"),
                    }
                ]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "serverName": _require(self.server_name, "trojan.server_name"),
                    "fingerprint": self.fingerprint,
                    "alpn": list(self.alpn),
                },
            },
            "tag": tag,
        }


ClientEndpoint = VlessRealityEndpoint | Hysteria2Endpoint | ShadowsocksEndpoint | TrojanTlsEndpoint


def build_happ_xray_profile(
    endpoints: list[ClientEndpoint],
    *,
    remarks: str = "UnLock VPN",
    auto_select: bool = True,
    probe_url: str = "http://www.gstatic.com/generate_204",
    loglevel: str = "Warning",
    direct_domains: tuple[str, ...] = DEFAULT_DIRECT_DOMAINS,
    direct_ips: tuple[str, ...] = DEFAULT_DIRECT_IPS,
    block_bittorrent: bool = True,
) -> dict[str, Any]:
    if not endpoints:
        raise ProfileError("at least one endpoint is required")

    proxy_tags: list[str] = []
    outbounds: list[dict[str, Any]] = []
    for endpoint in endpoints:
        tag = _proxy_tag(endpoint.tag)
        if tag in proxy_tags:
            raise ProfileError(f"duplicate endpoint tag: {tag}")
        proxy_tags.append(tag)
        outbounds.append(endpoint.to_xray_outbound(tag))

    outbounds.extend(
        [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ]
    )

    route_target = (
        {"balancerTag": "auto"} if auto_select and len(proxy_tags) > 1 else {"outboundTag": proxy_tags[0]}
    )
    rules: list[dict[str, Any]] = []
    if block_bittorrent:
        rules.append({"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"})
    if direct_domains:
        rules.append({"type": "field", "domain": list(direct_domains), "outboundTag": "direct"})
    if direct_ips:
        rules.append({"type": "field", "ip": list(direct_ips), "outboundTag": "direct"})
    rules.append({"type": "field", "network": "tcp,udp", **route_target})

    routing: dict[str, Any] = {
        "domainStrategy": "IPIfNonMatch",
        "rules": rules,
    }
    if auto_select and len(proxy_tags) > 1:
        routing["balancers"] = [
            {
                "tag": "auto",
                "selector": ["proxy-"],
                "fallbackTag": proxy_tags[0],
                "strategy": {"type": "leastPing"},
            }
        ]

    profile: dict[str, Any] = {
        "remarks": remarks,
        "log": {
            "loglevel": loglevel,
            "dnsLog": True,
        },
        "dns": {
            "tag": "dns-in",
            "queryStrategy": "UseIPv4",
            "servers": ["8.8.8.8", "9.9.9.9"],
        },
        "inbounds": [
            {
                "tag": "socks",
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {
                    "enabled": True,
                    "routeOnly": False,
                    "destOverride": ["http", "tls", "quic"],
                },
            },
            {
                "tag": "http",
                "listen": "127.0.0.1",
                "port": 10809,
                "protocol": "http",
                "settings": {"allowTransparent": False},
                "sniffing": {
                    "enabled": True,
                    "routeOnly": False,
                    "destOverride": ["http", "tls", "quic"],
                },
            },
        ],
        "outbounds": outbounds,
        "routing": routing,
    }

    if auto_select and len(proxy_tags) > 1:
        profile["burstObservatory"] = {
            "subjectSelector": ["proxy-"],
            "pingConfig": {
                "destination": probe_url,
                "connectivity": "",
                "interval": "1m",
                "sampling": 1,
                "timeout": "3s",
            },
        }

    return profile


def dumps_happ_xray_profile(profile: dict[str, Any], *, pretty: bool = True) -> str:
    if pretty:
        return json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    return json.dumps(profile, ensure_ascii=False, separators=(",", ":"))


def endpoint_from_dict(payload: dict[str, Any]) -> ClientEndpoint:
    protocol = str(payload.get("protocol") or payload.get("type") or "").lower().replace("-", "")
    if protocol in {"vless", "vlessreality", "reality"}:
        return VlessRealityEndpoint(
            tag=str(payload.get("tag") or "reality"),
            address=str(payload.get("address") or payload.get("server") or ""),
            port=int(payload.get("port") or payload.get("server_port") or 443),
            uuid=str(payload.get("uuid") or payload.get("id") or ""),
            public_key=str(payload.get("public_key") or payload.get("pbk") or ""),
            server_name=str(payload.get("server_name") or payload.get("sni") or payload.get("address") or ""),
            short_id=str(payload.get("short_id") or payload.get("sid") or ""),
            flow=str(payload.get("flow") or ""),
            fingerprint=str(payload.get("fingerprint") or payload.get("fp") or "firefox"),
            spider_x=str(
                payload["spider_x"]
                if "spider_x" in payload
                else payload["spx"]
                if "spx" in payload
                else ""
            ),
        )
    if protocol in {"hysteria", "hysteria2", "hy2"}:
        alpn = payload.get("alpn") or ["h3"]
        if isinstance(alpn, str):
            alpn = [alpn]
        return Hysteria2Endpoint(
            tag=str(payload.get("tag") or "hysteria2"),
            address=str(payload.get("address") or payload.get("server") or ""),
            port=int(payload.get("port") or payload.get("server_port") or 443),
            auth=str(payload.get("auth") or payload.get("password") or ""),
            server_name=str(payload.get("server_name") or payload.get("sni") or payload.get("address") or ""),
            fingerprint=str(payload.get("fingerprint") or payload.get("fp") or "chrome"),
            alpn=tuple(str(item) for item in alpn),
            congestion=str(payload.get("congestion") or "bbr"),
            pinned_peer_cert_sha256=(
                payload.get("pinned_peer_cert_sha256")
                or payload.get("pinnedPeerCertSha256")
                or payload.get("pin_sha256")
                or payload.get("pinSHA256")
            ),
        )
    if protocol in {"shadowsocks", "ss"}:
        return ShadowsocksEndpoint(
            tag=str(payload.get("tag") or "shadowsocks"),
            address=str(payload.get("address") or payload.get("server") or ""),
            port=int(payload.get("port") or payload.get("server_port") or 8388),
            password=str(payload.get("password") or ""),
            method=str(payload.get("method") or "chacha20-ietf-poly1305"),
        )
    if protocol in {"trojan", "trojantls"}:
        alpn = payload.get("alpn") or ["http/1.1"]
        if isinstance(alpn, str):
            alpn = [alpn]
        return TrojanTlsEndpoint(
            tag=str(payload.get("tag") or "trojan"),
            address=str(payload.get("address") or payload.get("server") or ""),
            port=int(payload.get("port") or payload.get("server_port") or 443),
            password=str(payload.get("password") or ""),
            server_name=str(payload.get("server_name") or payload.get("sni") or payload.get("address") or ""),
            fingerprint=str(payload.get("fingerprint") or payload.get("fp") or "chrome"),
            alpn=tuple(str(item) for item in alpn),
        )
    raise ProfileError(f"unsupported endpoint protocol: {protocol or '<missing>'}")


def endpoints_from_dicts(payloads: list[dict[str, Any]]) -> list[ClientEndpoint]:
    return [endpoint_from_dict(item) for item in payloads]
