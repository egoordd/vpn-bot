#!/usr/bin/env bash
#
# РУ-режим для роутеров на польском узле: второй интерфейс AmneziaWG (awg1)
# и xray, который делит TCP клиентов awg1 — российское через релей на VK,
# остальное напрямую. awg0 (весь трафик через Польшу) не трогается.
#
# Запуск на узле (root), config.json — на stdin (gen_xray_config.py):
#   PORT=40002 bash setup-pl.sh < config.json
set -euo pipefail
umask 022

PORT="${PORT:-40002}"
SUBNET=10.13.16.0/24
SRVIP=10.13.16.1/24
REDIR=12345
CFGDIR=/etc/amnezia/amneziawg
APP=/opt/awg-ru
IFACE="$(ip route get 1.1.1.1 | grep -oP 'dev \K\S+')"

ss -lun | grep -q ":$PORT " && { echo "порт $PORT занят"; exit 1; }

echo "== xray для РУ-режима ($APP)"
mkdir -p "$APP"
cat > "$APP/config.json.new"
docker run --rm -v "$APP/config.json.new:/etc/xray/config.json:ro" \
  --entrypoint /usr/local/bin/xray ghcr.io/xtls/xray-core:latest run -test -c /etc/xray/config.json >/dev/null
mv "$APP/config.json.new" "$APP/config.json"
chmod 600 "$APP/config.json"
cat > "$APP/docker-compose.yml" <<YML
services:
  awg-ru:
    image: ghcr.io/xtls/xray-core:latest
    container_name: awg-ru
    restart: always
    network_mode: host
    user: "0:0"
    command: ["run", "-c", "/etc/xray/config.json"]
    volumes:
      - $APP/config.json:/etc/xray/config.json:ro
YML
(cd "$APP" && docker compose up -d)

echo "== awg1 (порт $PORT, подсеть $SUBNET)"
cd "$CFGDIR"; umask 077
[ -s awg1_private.key ] || { awg genkey > awg1_private.key; awg pubkey < awg1_private.key > awg1_public.key; }
param() { awk -F' *= *' -v k="$1" '$1==k{print $2; exit}' awg0.conf; }
cat > awg1.conf <<CONF
[Interface]
Address = $SRVIP
ListenPort = $PORT
PrivateKey = $(cat awg1_private.key)
Jc = $(param Jc)
Jmin = $(param Jmin)
Jmax = $(param Jmax)
S1 = $(param S1)
S2 = $(param S2)
H1 = $(param H1)
H2 = $(param H2)
H3 = $(param H3)
H4 = $(param H4)
PostUp = iptables -t nat -A PREROUTING -i awg1 -p tcp -j REDIRECT --to-ports $REDIR; iptables -t nat -A POSTROUTING -s $SUBNET -o $IFACE -j MASQUERADE; iptables -I FORWARD -i awg1 -p udp --dport 443 -j REJECT; iptables -A FORWARD -i awg1 -j ACCEPT; iptables -A FORWARD -o awg1 -j ACCEPT
PostDown = iptables -t nat -D PREROUTING -i awg1 -p tcp -j REDIRECT --to-ports $REDIR; iptables -t nat -D POSTROUTING -s $SUBNET -o $IFACE -j MASQUERADE; iptables -D FORWARD -i awg1 -p udp --dport 443 -j REJECT; iptables -D FORWARD -i awg1 -j ACCEPT; iptables -D FORWARD -o awg1 -j ACCEPT
CONF
chmod 600 awg1.conf
systemctl enable --now awg-quick@awg1

if ufw status | grep -q '^Status: active'; then
  ufw allow "$PORT/udp" comment amneziawg-ru
  ufw allow in on awg1 to any port "$REDIR" proto tcp comment awg-ru-redirect
fi

echo "== готово"
awg show awg1 | sed -n 1,4p
docker ps --filter name=awg-ru --format '{{.Names}} {{.Status}}'
