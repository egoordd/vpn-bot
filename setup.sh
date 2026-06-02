#!/usr/bin/env bash
# =============================================================================
# vpn-bot — one-shot server setup
# Docker + AmneziaWG (DPI-bypass, obfuscated WireGuard) + the bot.
#
# Run as root on a FRESH server (Ubuntu 24.04 LTS recommended). Idempotent:
# safe to re-run. Survives reboots (awg0 is enabled via systemd).
#
# Usage:
#   git clone <repo> ~/vpn-bot && cd ~/vpn-bot
#   cp .env.example .env   # then fill BOT_TOKEN / CRYPTOBOT_TOKEN / DB creds
#   ./setup.sh
# =============================================================================
set -euo pipefail

# ---- fixed settings (obfuscation params MUST match bot defaults in config.py) ----
AWG_DIR="/etc/amnezia/amneziawg"
AWG_CONF="$AWG_DIR/awg0.conf"
AWG_PORT="51821"
AWG_SERVER_IP="10.9.0.1"
AWG_POOL="10.9.0.0/24"
DNS="1.1.1.1"
JC=4; JMIN=40; JMAX=70; S1=50; S2=100
H1=1234567; H2=2345678; H3=3456789; H4=4567890

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log(){ printf '\n=== %s ===\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Run as root."; exit 1; }
export DEBIAN_FRONTEND=noninteractive

log "Base packages"
apt-get update -y
apt-get install -y curl git qrencode iptables ca-certificates software-properties-common

log "Docker"
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
docker compose version >/dev/null 2>&1 || apt-get install -y docker-compose-plugin

log "AmneziaWG"
if ! command -v awg >/dev/null; then
  apt-get install -y "linux-headers-$(uname -r)" 2>/dev/null || true
  add-apt-repository -y ppa:amnezia/ppa 2>/dev/null || true
  apt-get update -y 2>/dev/null || true
  apt-get install -y amneziawg 2>/dev/null || true
fi
if ! command -v awg >/dev/null; then
  log "PPA package unavailable for this release — building AmneziaWG from source (userspace)"
  apt-get install -y build-essential make golang-go
  rm -rf /opt/amneziawg-tools /opt/amneziawg-go
  git clone --branch v1.0.20260223 --depth 1 https://github.com/amnezia-vpn/amneziawg-tools /opt/amneziawg-tools
  ( cd /opt/amneziawg-tools/src && make && make install )
  git clone --branch v0.2.18 --depth 1 https://github.com/amnezia-vpn/amneziawg-go /opt/amneziawg-go
  ( cd /opt/amneziawg-go && make && cp amneziawg-go /usr/bin/ )
fi
command -v awg >/dev/null || { echo "AmneziaWG install failed."; exit 1; }

# kernel module if present, else userspace (amneziawg-go)
USERSPACE=1
if modprobe amneziawg 2>/dev/null; then USERSPACE=0; fi
[ "$USERSPACE" = 1 ] && ! command -v amneziawg-go >/dev/null && { echo "No kernel module and no amneziawg-go."; exit 1; }

log "IP forwarding"
echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-awg.conf
sysctl -w net.ipv4.ip_forward=1 >/dev/null

EXT_IF="$(ip route show default | awk '/default/{print $5; exit}')"
PUB_IP="$(curl -4 -s --max-time 10 https://api.ipify.org || true)"
[ -n "$EXT_IF" ] || { echo "Cannot detect external interface."; exit 1; }
[ -n "$PUB_IP" ] || { echo "Cannot detect public IPv4."; exit 1; }
echo "$PUB_IP" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || { echo "Detected public IP is not a valid IPv4: $PUB_IP"; exit 1; }
log "External interface: $EXT_IF | Public IP: $PUB_IP"

log "Server keypair"
mkdir -p "$AWG_DIR"
if [ ! -f "$AWG_DIR/server_private.key" ]; then
  awg genkey > "$AWG_DIR/server_private.key"
  awg pubkey < "$AWG_DIR/server_private.key" > "$AWG_DIR/server_public.key"
fi
SPRIV="$(cat "$AWG_DIR/server_private.key")"
SPUB="$(cat "$AWG_DIR/server_public.key")"
chmod 600 "$AWG_DIR/server_private.key"

log "awg0.conf"
cat > "$AWG_CONF" <<EOF
[Interface]
Address = $AWG_SERVER_IP/24
ListenPort = $AWG_PORT
PrivateKey = $SPRIV
Jc = $JC
Jmin = $JMIN
Jmax = $JMAX
S1 = $S1
S2 = $S2
H1 = $H1
H2 = $H2
H3 = $H3
H4 = $H4
PostUp = iptables -A FORWARD -i awg0 -j ACCEPT; iptables -A FORWARD -o awg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $EXT_IF -j MASQUERADE
PostDown = iptables -D FORWARD -i awg0 -j ACCEPT; iptables -D FORWARD -o awg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $EXT_IF -j MASQUERADE
EOF
chmod 600 "$AWG_CONF"

log "Bring up awg0 (persistent across reboots)"
if [ "$USERSPACE" = 1 ]; then
  mkdir -p /etc/systemd/system/awg-quick@awg0.service.d
  cat > /etc/systemd/system/awg-quick@awg0.service.d/override.conf <<EOF
[Service]
Environment=WG_QUICK_USERSPACE_IMPLEMENTATION=amneziawg-go
EOF
  systemctl daemon-reload
fi
systemctl enable awg-quick@awg0 >/dev/null 2>&1 || true
if ! systemctl restart awg-quick@awg0 2>/dev/null; then
  WG_QUICK_USERSPACE_IMPLEMENTATION=amneziawg-go awg-quick down awg0 2>/dev/null || true
  WG_QUICK_USERSPACE_IMPLEMENTATION=amneziawg-go awg-quick up awg0
fi

log "Bot .env (preserves your secrets, fills server-specific values)"
ENV_FILE="$REPO_DIR/.env"
[ -f "$ENV_FILE" ] || { echo "MISSING $ENV_FILE. Create it from .env.example (BOT_TOKEN, CRYPTOBOT_TOKEN, DB creds) and re-run."; exit 1; }
upsert(){ local k="$1" v="$2"; if grep -q "^$k=" "$ENV_FILE"; then sed -i "s#^$k=.*#$k=$v#" "$ENV_FILE"; else printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"; fi; }
upsert WG_INTERFACE awg0
upsert WG_SERVER_PUBLIC_KEY "$SPUB"
upsert WG_SERVER_ENDPOINT "$PUB_IP:$AWG_PORT"
upsert WG_CLIENT_ADDRESS_POOL "$AWG_POOL"
upsert WG_CLIENT_DNS "$DNS"
upsert WG_ALLOWED_IPS "0.0.0.0/0"

log "Bot stack (docker compose build + up)"
( cd "$REPO_DIR" && docker compose up -d --build )

log "Test client QR (verify before relying on the bot)"
CPRIV="$(awg genkey)"; CPUB="$(echo "$CPRIV" | awg pubkey)"
awg set awg0 peer "$CPUB" allowed-ips 10.9.0.250/32
cat > /root/awg_test_client.conf <<EOF
[Interface]
PrivateKey = $CPRIV
Address = 10.9.0.250/32
DNS = $DNS
Jc = $JC
Jmin = $JMIN
Jmax = $JMAX
S1 = $S1
S2 = $S2
H1 = $H1
H2 = $H2
H3 = $H3
H4 = $H4

[Peer]
PublicKey = $SPUB
Endpoint = $PUB_IP:$AWG_PORT
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF
qrencode -t ansiutf8 < /root/awg_test_client.conf

printf '\n=== DONE ===\n'
printf 'Server pubkey : %s\n' "$SPUB"
printf 'Endpoint      : %s:%s\n' "$PUB_IP" "$AWG_PORT"
printf 'Scan the QR above with the AmneziaWG app to verify, then use the bot (Получить ключ).\n'
