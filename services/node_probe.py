"""Live reachability check of a user's own servers.

When a user can't connect, the highest-leverage help is telling them which
locations actually respond *right now* so they pick a working one instead of
giving up. We fetch the user's real subscription from the gateway, parse the
TCP endpoints (VLESS/Trojan — Hysteria2 is UDP and can't be TCP-probed) and
open a short TCP connection to each, grouped by location.

Best-effort and fail-open: any error yields an empty result and the caller
falls back to plain guidance, never a scary "everything is down".
"""
from __future__ import annotations

import asyncio
import base64
import urllib.parse
import urllib.request
from dataclasses import dataclass

_PROBE_TIMEOUT = 3.0
_FETCH_TIMEOUT = 8.0
# TCP-probable schemes (xray/TLS). Hysteria2 is UDP → skipped, inherits nothing.
_TCP_SCHEMES = ("vless", "trojan", "vmess", "ss")


@dataclass(frozen=True)
class LocationHealth:
    flag: str
    name: str
    reachable: bool


def _location_key(remark: str) -> tuple[str, str]:
    """Split a remark like "🇺🇸 США · Trojan" into (flag, name) for grouping.

    The part before " · " is the location; the protocol suffix is dropped so
    a location's VLESS and Trojan endpoints group together.
    """
    base = remark.split(" · ", 1)[0].strip()
    parts = base.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", base


def _endpoint(uri: str) -> tuple[str, int] | None:
    try:
        after_at = uri.split("://", 1)[1].split("@", 1)[1]
    except IndexError:
        return None
    hostport = after_at.split("?", 1)[0].split("#", 1)[0].split("/", 1)[0]
    host = hostport.split(":", 1)[0]
    if not host:
        return None
    port = 443
    if ":" in hostport:
        try:
            port = int(hostport.rsplit(":", 1)[1])
        except ValueError:
            return None
    return host, port


def parse_location_endpoints(decoded: str) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """Map each location (flag, name) to its TCP-probable host:port endpoints."""
    targets: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for line in decoded.splitlines():
        line = line.strip()
        scheme = line.split("://", 1)[0].lower() if "://" in line else ""
        if scheme not in _TCP_SCHEMES:
            continue
        endpoint = _endpoint(line)
        if endpoint is None:
            continue
        remark = urllib.parse.unquote(line.split("#", 1)[1]) if "#" in line else ""
        key = _location_key(remark)
        targets.setdefault(key, [])
        if endpoint not in targets[key]:
            targets[key].append(endpoint)
    return targets


async def _tcp_ok(host: str, port: int) -> bool:
    try:
        fut = asyncio.open_connection(host, port)
        _, writer = await asyncio.wait_for(fut, timeout=_PROBE_TIMEOUT)
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except (OSError, asyncio.TimeoutError):
        pass
    return True


async def _location_reachable(endpoints: list[tuple[str, int]]) -> bool:
    # A location is up if ANY of its TCP endpoints answers.
    results = await asyncio.gather(*(_tcp_ok(h, p) for h, p in endpoints))
    return any(results)


def _fetch_decoded(sub_url: str) -> str:
    req = urllib.request.Request(sub_url, headers={"User-Agent": "v2rayNG/1.8.5"})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", "replace").strip()
    if not raw:
        return ""
    try:
        return base64.b64decode(raw + "===").decode("utf-8", "replace")
    except Exception:
        return raw


async def probe_subscription(sub_url: str) -> list[LocationHealth]:
    """Fetch the subscription and probe each location. Empty list on any error
    (caller then shows guidance without a health line)."""
    if not sub_url:
        return []
    try:
        decoded = await asyncio.to_thread(_fetch_decoded, sub_url)
    except Exception:
        return []
    targets = parse_location_endpoints(decoded)
    if not targets:
        return []
    checks = await asyncio.gather(
        *(_location_reachable(endpoints) for endpoints in targets.values())
    )
    return [
        LocationHealth(flag=key[0], name=key[1], reachable=reachable)
        for key, reachable in zip(targets.keys(), checks)
    ]
