#!/usr/bin/env bash
#
# Stand up an AmneziaWG server on an Ubuntu 24.04 node (idempotent).
#
# The obfuscation params (Jc/Jmin/Jmax/S1/S2/H1-H4) MUST match the bot's
# config.py AWG_* defaults, otherwise client handshakes fail.
#
# Usage (run as root on the node):
#   SUBNET=10.13.13.0/24 SRVIP=10.13.13.1/24 PORT=51820 ./setup-node.sh
#
# Live nodes (see deploy/amneziawg/README.md):
#   US -> SUBNET=10.13.13.0/24 SRVIP=10.13.13.1/24
#   NL -> SUBNET=10.13.14.0/24 SRVIP=10.13.14.1/24
#
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

PORT="${PORT:-51820}"
SUBNET="${SUBNET:?set SUBNET, e.g. 10.13.13.0/24}"
SRVIP="${SRVIP:?set SRVIP, e.g. 10.13.13.1/24}"
CFGDIR=/etc/amnezia/amneziawg
KREL="$(uname -r)"
IFACE="$(ip route get 1.1.1.1 | grep -oP 'dev \K\S+')"

# --- install AmneziaWG (DKMS kernel module + tools) ---
dpkg -l "linux-headers-$KREL" 2>/dev/null | grep -q '^ii' || apt-get install -y "linux-headers-$KREL"
apt-get install -y software-properties-common
add-apt-repository -y ppa:amnezia/ppa
apt-get update
apt-get install -y amneziawg-dkms amneziawg-tools
modprobe amneziawg

# --- server keypair (idempotent) ---
mkdir -p "$CFGDIR"; chmod 700 "$CFGDIR"; cd "$CFGDIR"; umask 077
if [ ! -s server_private.key ]; then
  awg genkey > server_private.key
  awg pubkey < server_private.key > server_public.key
fi

# --- awg0 config: obfuscation params + NAT for the tunnel subnet ---
cat > awg0.conf <<CONF
[Interface]
Address = $SRVIP
ListenPort = $PORT
PrivateKey = $(cat server_private.key)
Jc = 4
Jmin = 40
Jmax = 70
S1 = 50
S2 = 100
H1 = 1234567
H2 = 2345678
H3 = 3456789
H4 = 4567890
PostUp = iptables -t nat -A POSTROUTING -s $SUBNET -o $IFACE -j MASQUERADE; iptables -A FORWARD -i awg0 -j ACCEPT; iptables -A FORWARD -o awg0 -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -s $SUBNET -o $IFACE -j MASQUERADE; iptables -D FORWARD -i awg0 -j ACCEPT; iptables -D FORWARD -o awg0 -j ACCEPT
CONF
chmod 600 awg0.conf

# --- enable forwarding + bring up + persist across reboot ---
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-amneziawg.conf
sysctl -p /etc/sysctl.d/99-amneziawg.conf
awg-quick down awg0 2>/dev/null || true
awg-quick up awg0
systemctl enable awg-quick@awg0

echo "server public key: $(cat server_public.key)"
awg show awg0 | head -6
