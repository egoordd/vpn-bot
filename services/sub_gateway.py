#!/usr/bin/env python3
"""Multi-protocol subscription gateway.

Wraps the Marzban subscription: fetches the user's VLESS Reality links from the
panel (token-authed, so it's per-user and respects status/expiry) and appends a
Hysteria2 entry for each location the user has. The client imports ONE link and
sees both protocols per location, e.g. 🇺🇸 США VLESS + Hysteria2, 🇳🇱 Нидерланды
VLESS + Hysteria2.

Runs on the main server next to Marzban. Stdlib only (no pip deps).

Env:
  MARZBAN_BASE   e.g. https://144.172.101.217.sslip.io:8443
  US_HY2_PASS    Hysteria2 password on the US node
  NL_HY2_PASS    Hysteria2 password on the NL node
  LISTEN_PORT    default 8090 (bind 127.0.0.1; nginx proxies a public path)
"""
from __future__ import annotations

import base64
import os
import ssl
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARZBAN_BASE = os.environ.get("MARZBAN_BASE", "https://144.172.101.217.sslip.io:8443").rstrip("/")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8090"))
BIND_HOST = os.environ.get("BIND_HOST", "127.0.0.1")
CERT_FILE = os.environ.get("CERT_FILE", "")  # when set -> serve HTTPS on BIND_HOST
KEY_FILE = os.environ.get("KEY_FILE", "")

# vless host -> location + its Hysteria2 endpoint
NODES = {
    "144.172.101.217.sslip.io": {
        "flag": "🇺🇸", "name": "США",
        "hy2_host": "144.172.101.217.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("US_HY2_PASS", ""),
    },
    "107.189.22.160.sslip.io": {
        "flag": "🇳🇱", "name": "Нидерланды",
        "hy2_host": "107.189.22.160.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("NL_HY2_PASS", ""),
    },
}

# The gateway calls our own Marzban panel (same host in prod), so TLS
# verification is unnecessary here and trips on the own-domain sslip cert.
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _vless_host(uri: str) -> str | None:
    try:
        after_at = uri.split("@", 1)[1]
        return after_at.split(":", 1)[0]
    except IndexError:
        return None


def _hy2_uri(node: dict) -> str:
    remark = urllib.parse.quote(f"{node['flag']} {node['name']} · Hysteria2")
    host, port = node["hy2_host"], node["hy2_port"]
    return (
        f"hysteria2://{node['hy2_pass']}@{host}:{port}"
        f"?sni={host}&insecure=0#{remark}"
    )


def _fetch_marzban_sub(token: str) -> tuple[str, str | None] | None:
    """Returns (decoded_uris_text, userinfo_header) or None if invalid."""
    url = f"{MARZBAN_BASE}/sub/{token}"
    req = urllib.request.Request(url, headers={"User-Agent": "v2rayNG/1.8.5"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
            raw = resp.read().decode("utf-8", "replace").strip()
            userinfo = resp.headers.get("subscription-userinfo")
    except Exception:
        return None
    try:
        decoded = base64.b64decode(raw + "===").decode("utf-8", "replace")
    except Exception:
        decoded = raw
    return decoded, userinfo


def build_combined(token: str) -> tuple[str, str | None] | None:
    fetched = _fetch_marzban_sub(token)
    if fetched is None:
        return None
    decoded, userinfo = fetched
    vless_uris = [line.strip() for line in decoded.splitlines() if line.strip().startswith("vless://")]
    if not vless_uris:
        return "", userinfo

    combined: list[str] = []
    for uri in vless_uris:
        combined.append(uri)
        host = _vless_host(uri)
        node = NODES.get(host) if host else None
        if node and node["hy2_pass"]:
            combined.append(_hy2_uri(node))

    payload = base64.b64encode("\n".join(combined).encode("utf-8")).decode("ascii")
    return payload, userinfo


class Handler(BaseHTTPRequestHandler):
    server_version = "unlock-subgw"

    def log_message(self, *args):  # silence default logging
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/health", "/healthz"):
            self._send(200, b"ok", "text/plain")
            return
        prefix = "/sub/"
        if not path.startswith(prefix):
            self._send(404, b"not found", "text/plain")
            return
        token = path[len(prefix):].split("/", 1)[0]
        if not token:
            self._send(404, b"not found", "text/plain")
            return
        result = build_combined(token)
        if result is None:
            self._send(404, b"invalid subscription", "text/plain")
            return
        payload, userinfo = result
        extra = {"subscription-userinfo": userinfo} if userinfo else {}
        self._send(200, payload.encode("ascii"), "text/plain; charset=utf-8", extra)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Profile-Update-Interval", "12")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((BIND_HOST, LISTEN_PORT), Handler)
    scheme = "http"
    if CERT_FILE and KEY_FILE:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    print(f"sub-gateway on {scheme}://{BIND_HOST}:{LISTEN_PORT}, marzban={MARZBAN_BASE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
