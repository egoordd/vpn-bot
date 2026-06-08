#!/usr/bin/env bash
# =============================================================================
# Reality smoke test — ставит Xray + один VLESS+Reality инбаунд и печатает
# QR/ссылку для импорта в клиент. Цель: за ~15 минут проверить, пробивает ли
# VLESS+Reality твоего мобильного оператора. Домен НЕ нужен.
# Запуск от root на чистом Ubuntu/Debian:  bash reality_smoketest.sh
# =============================================================================
set -euo pipefail

SNI=$(printf '%s' "www.microsoft.com" | grep -oiE '[a-z0-9.-]+\.[a-z]{2,}' | head -1)  # дест-домен (устойчив к авто-ссылкам при вставке)
PORT=443

[ "$(id -u)" = 0 ] || { echo "Запускай от root"; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "=== Ставлю зависимости + Xray ==="
apt-get update -y
apt-get install -y curl qrencode openssl
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

echo "=== Генерю ключи ==="
UUID=$(xray uuid)
read -r PRIV PUB <<<"$(xray x25519 | grep -oE '[A-Za-z0-9_-]{43,44}' | head -2 | tr '\n' ' ')"
[ -n "$PRIV" ] && [ -n "$PUB" ] || { echo "keygen parse failed, raw output:"; xray x25519; exit 1; }
SID=$(openssl rand -hex 8)
IP=$(curl -4 -s --max-time 10 https://api.ipify.org)

cat > /usr/local/etc/xray/config.json <<EOF
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "listen": "0.0.0.0",
      "port": $PORT,
      "protocol": "vless",
      "settings": {
        "clients": [ { "id": "$UUID", "flow": "xtls-rprx-vision" } ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "$SNI:443",
          "xver": 0,
          "serverNames": [ "$SNI" ],
          "privateKey": "$PRIV",
          "shortIds": [ "$SID" ]
        }
      }
    }
  ],
  "outbounds": [ { "protocol": "freedom" } ]
}
EOF

# на всякий случай открыть порт, если активен ufw
ufw allow ${PORT}/tcp >/dev/null 2>&1 || true

systemctl enable xray >/dev/null 2>&1 || true
systemctl restart xray
sleep 1
systemctl is-active xray >/dev/null && echo "Xray запущен ✅" || { echo "Xray не поднялся ❌"; journalctl -u xray --no-pager -n 20; exit 1; }

LINK="vless://${UUID}@${IP}:${PORT}?type=tcp&security=reality&pbk=${PUB}&fp=chrome&sni=${SNI}&sid=${SID}&flow=xtls-rprx-vision&encryption=none#RealitySmokeTest"

echo
echo "================= ССЫЛКА VLESS ================="
echo "$LINK"
echo
echo "===================== QR ======================="
qrencode -t ansiutf8 "$LINK"
echo
echo "Импортируй ссылку/QR в V2RayTun, включи на мобильном интернете, открой ya.ru"
