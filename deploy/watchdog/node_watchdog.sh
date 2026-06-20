#!/usr/bin/env bash
# Health watchdog for UnLock VPN nodes/services. Runs on the bot VPS via a
# systemd timer. Network-only checks (no traffic through this box). Sends a
# Telegram alert to the SEPARATE alerts bot on state transitions (down/recover).
set -u

ENV_FILE="${ENV_FILE:-/opt/vpn-bot/.env}"
STATE_DIR="${STATE_DIR:-/var/lib/node-watchdog}"
mkdir -p "$STATE_DIR"

ALERT_TOKEN=$(sed -n 's/^ALERTS_BOT_TOKEN=//p' "$ENV_FILE")
ALERT_CHAT=$(sed -n 's/^ALERTS_CHAT_ID=//p' "$ENV_FILE")
[ -n "$ALERT_CHAT" ] || ALERT_CHAT=$(sed -n 's/^ADMIN_IDS=//p' "$ENV_FILE" | cut -d, -f1)

notify() {
  [ -n "$ALERT_TOKEN" ] && [ -n "$ALERT_CHAT" ] || return 0
  curl -s -m 15 "https://api.telegram.org/bot${ALERT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${ALERT_CHAT}" \
    --data-urlencode "text=$1" \
    -d parse_mode=HTML >/dev/null
}

# report <state-key> <human label> <exit-status: 0=ok>
report() {
  local sf="$STATE_DIR/$1" prev
  prev=$(cat "$sf" 2>/dev/null || echo up)
  if [ "$3" -eq 0 ]; then
    [ "$prev" = down ] && notify "✅ <b>$2</b> снова в строю"
    echo up >"$sf"
  else
    [ "$prev" = up ] && notify "🔴 <b>$2</b> не отвечает"
    echo down >"$sf"
  fi
}

reality() {
  echo | timeout 12 openssl s_client -connect "$1:443" -servername "$2" 2>/dev/null \
    | openssl x509 -noout -subject 2>/dev/null | grep -q .
}

reality 144.172.101.217 144.172.101.217.sslip.io
report reality_us "🇺🇸 США · VLESS Reality :443" $?

reality 107.189.22.160 107.189.22.160.sslip.io
report reality_nl "🇳🇱 Нидерланды · VLESS Reality :443" $?

curl -sk -m 10 -o /dev/null https://144.172.101.217.sslip.io:8443/
report panel "Marzban панель :8443" $?

[ "$(curl -sk -m 10 https://sub.unlockvpn.org:8444/health 2>/dev/null)" = ok ]
report gateway "Шлюз подписок :8444" $?
