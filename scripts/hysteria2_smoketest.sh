#!/usr/bin/env bash
# Hysteria2 smoke test for Phase 0.
#
# Runs Hysteria2 on 443/udp using Docker host networking and prints an import link.
# TCP/443 remains available for Remnawave/Xray; Hysteria2 only needs UDP.
#
# Usage on the VPS as root:
#   bash scripts/hysteria2_smoketest.sh
#
# Optional env:
#   PORT=443 SNI=www.microsoft.com MASQUERADE_URL=https://www.microsoft.com

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

PORT="${PORT:-443}"
SNI="${SNI:-www.microsoft.com}"
MASQUERADE_URL="${MASQUERADE_URL:-https://www.microsoft.com}"
BASE_DIR="${BASE_DIR:-/opt/hysteria2-smoke}"
COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
CONFIG_FILE="${BASE_DIR}/config.yaml"
CERT_FILE="${BASE_DIR}/server.crt"
KEY_FILE="${BASE_DIR}/server.key"
LINK_FILE="${BASE_DIR}/link.txt"
CLIENT_JSON_FILE="${BASE_DIR}/happ-hysteria.json"

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker.io
fi

mkdir -p "${BASE_DIR}"
chmod 700 "${BASE_DIR}"

# Stop earlier standalone Xray smoke processes that may occupy udp/443.
for pid_file in \
  /opt/xray-443-ss/xray.pid \
  /opt/xray-443-noflow/xray.pid \
  /opt/xray-443-clean/xray.pid
do
  if [[ -f "${pid_file}" ]]; then
    kill "$(cat "${pid_file}")" 2>/dev/null || true
    rm -f "${pid_file}"
  fi
done

PASSWORD="$(openssl rand -hex 16)"

openssl req \
  -x509 \
  -nodes \
  -newkey rsa:2048 \
  -keyout "${KEY_FILE}" \
  -out "${CERT_FILE}" \
  -days 365 \
  -subj "/CN=${SNI}" \
  -addext "subjectAltName=DNS:${SNI}" >/dev/null 2>&1

PINNED_PEER_CERT_SHA256="$(openssl x509 -outform der -in "${CERT_FILE}" | openssl dgst -sha256 | awk '{print $2}')"

cat > "${CONFIG_FILE}" <<EOF
listen: :${PORT}

tls:
  cert: /etc/hysteria/server.crt
  key: /etc/hysteria/server.key

auth:
  type: password
  password: ${PASSWORD}

masquerade:
  type: proxy
  proxy:
    url: ${MASQUERADE_URL}
    rewriteHost: true
EOF

cat > "${COMPOSE_FILE}" <<'EOF'
services:
  hysteria2:
    image: tobyxdd/hysteria:latest
    container_name: hysteria2-smoke
    network_mode: host
    restart: unless-stopped
    command: ["server", "-c", "/etc/hysteria/config.yaml"]
    volumes:
      - /opt/hysteria2-smoke:/etc/hysteria:ro
EOF

docker compose -f "${COMPOSE_FILE}" up -d --pull always

if [[ -d /opt/remnanode ]]; then
  (cd /opt/remnanode && docker compose up -d remnanode) || true
fi

IP="$(curl -4fsS https://api.ipify.org || true)"
if [[ -z "${IP}" ]]; then
  IP="$(hostname -I | awk '{print $1}')"
fi

LINK="hysteria2://${PASSWORD}@${IP}:${PORT}/?insecure=1&sni=${SNI}#hy2-smoke"
printf '%s\n' "${LINK}" > "${LINK_FILE}"

cat > "${CLIENT_JSON_FILE}" <<EOF
{
  "dns": {
    "queryStrategy": "UseIPv4",
    "servers": [
      "8.8.8.8",
      "9.9.9.9"
    ],
    "tag": "dns-in"
  },
  "inbounds": [
    {
      "listen": "127.0.0.1",
      "port": 10808,
      "protocol": "socks",
      "settings": {
        "auth": "noauth",
        "udp": true
      },
      "sniffing": {
        "destOverride": [
          "http",
          "tls",
          "quic"
        ],
        "enabled": true,
        "routeOnly": false
      },
      "tag": "socks"
    },
    {
      "listen": "127.0.0.1",
      "port": 10809,
      "protocol": "http",
      "settings": {
        "allowTransparent": false
      },
      "sniffing": {
        "destOverride": [
          "http",
          "tls",
          "quic"
        ],
        "enabled": true,
        "routeOnly": false
      },
      "tag": "http"
    }
  ],
  "log": {
    "dnsLog": true,
    "loglevel": "Warning"
  },
  "outbounds": [
    {
      "protocol": "hysteria",
      "settings": {
        "address": "${IP}",
        "port": ${PORT},
        "version": 2
      },
      "streamSettings": {
        "finalmask": {
          "quicParams": {
            "congestion": "bbr",
            "debug": false
          }
        },
        "hysteriaSettings": {
          "auth": "${PASSWORD}",
          "version": 2
        },
        "network": "hysteria",
        "security": "tls",
        "tlsSettings": {
          "alpn": [
            "h3"
          ],
          "fingerprint": "chrome",
          "serverName": "${SNI}",
          "pinnedPeerCertSha256": "${PINNED_PEER_CERT_SHA256}"
        }
      },
      "tag": "proxy"
    },
    {
      "protocol": "freedom",
      "tag": "direct"
    },
    {
      "protocol": "blackhole",
      "tag": "block"
    }
  ],
  "remarks": "hy2-smoke",
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      {
        "outboundTag": "block",
        "protocol": [
          "bittorrent"
        ],
        "type": "field"
      }
    ]
  }
}
EOF

echo "Hysteria2 smoke is running:"
echo "  UDP: ${IP}:${PORT}"
echo "  SNI: ${SNI}"
echo "  Password: ${PASSWORD}"
echo "  Link: ${LINK}"
echo "  Pinned cert SHA-256: ${PINNED_PEER_CERT_SHA256}"
echo "  Happ JSON: ${CLIENT_JSON_FILE}"
echo
echo "Status:"
docker compose -f "${COMPOSE_FILE}" ps
ss -lunp | grep -E ":${PORT}\b" || true

if command -v qrencode >/dev/null 2>&1; then
  echo
  qrencode -t ANSIUTF8 "${LINK}"
fi
