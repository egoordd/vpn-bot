#!/usr/bin/env bash
# =============================================================================
# Reality smoke test — ставит nginx + Let's Encrypt + Xray VLESS Reality и
# печатает QR/ссылку для импорта в клиент.
#
# Важно: после live-проверки 2026-06-08 НЕ используем чужой SNI вроде
# www.microsoft.com. Рабочая схема — own-domain/self-steal:
#   address == sni == IP.sslip.io или твой домен, который резолвится в IP ноды
#   Reality dest -> HTTPS на этой же ноде с валидным сертификатом.
#
# Запуск от root на чистом Ubuntu/Debian:
#   bash reality_smoketest.sh
#
# Опционально:
#   DOMAIN=node.example.com PORT=443 DEST_PORT=8443 bash reality_smoketest.sh
# =============================================================================
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Запускай от root"; exit 1; }
export DEBIAN_FRONTEND=noninteractive

PORT="${PORT:-443}"
DEST_PORT="${DEST_PORT:-8443}"
FINGERPRINT="${FINGERPRINT:-firefox}"
IP="${IP:-}"
DOMAIN="${DOMAIN:-}"

echo "=== Ставлю зависимости + Xray ==="
apt-get update -y
apt-get install -y curl qrencode openssl nginx certbot
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

if [ -z "$IP" ]; then
  IP="$(curl -4 -s --max-time 10 https://api.ipify.org || true)"
fi
if [ -z "$IP" ]; then
  echo "Не удалось определить внешний IPv4. Передай IP=1.2.3.4 вручную."
  exit 1
fi
if [ -z "$DOMAIN" ]; then
  DOMAIN="${IP}.sslip.io"
fi

echo "=== Готовлю HTTPS self-steal dest: ${DOMAIN}:${DEST_PORT} ==="
mkdir -p /var/www/reality-smoke/.well-known/acme-challenge
chown -R www-data:www-data /var/www/reality-smoke
rm -f /etc/nginx/sites-enabled/default

cat > /etc/nginx/sites-available/reality-smoke.conf <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    root /var/www/reality-smoke;

    location /.well-known/acme-challenge/ {
        try_files \$uri =404;
    }

    location / {
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }
}
EOF

ln -sf /etc/nginx/sites-available/reality-smoke.conf /etc/nginx/sites-enabled/reality-smoke.conf
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl restart nginx

certbot certonly \
  --webroot \
  --webroot-path /var/www/reality-smoke \
  --domain "${DOMAIN}" \
  --agree-tos \
  --register-unsafely-without-email \
  --non-interactive

cat > /etc/nginx/sites-available/reality-smoke.conf <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    root /var/www/reality-smoke;

    location /.well-known/acme-challenge/ {
        try_files \$uri =404;
    }

    location / {
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }
}

server {
    listen ${DEST_PORT} ssl;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        return 200 "reality smoke\n";
        add_header Content-Type text/plain;
    }
}
EOF

nginx -t
systemctl restart nginx

echo "=== Генерю ключи ==="
UUID=$(xray uuid)
read -r PRIV PUB <<<"$(xray x25519 | grep -oE '[A-Za-z0-9_-]{43,44}' | head -2 | tr '\n' ' ')"
[ -n "$PRIV" ] && [ -n "$PUB" ] || { echo "keygen parse failed, raw output:"; xray x25519; exit 1; }
SID=$(openssl rand -hex 8)

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
          "dest": "$IP:$DEST_PORT",
          "xver": 0,
          "serverNames": [ "$DOMAIN" ],
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
ufw allow 80/tcp >/dev/null 2>&1 || true
ufw allow ${PORT}/tcp >/dev/null 2>&1 || true
ufw allow ${DEST_PORT}/tcp >/dev/null 2>&1 || true

systemctl enable xray >/dev/null 2>&1 || true
systemctl restart xray
sleep 1
systemctl is-active xray >/dev/null && echo "Xray запущен ✅" || { echo "Xray не поднялся ❌"; journalctl -u xray --no-pager -n 20; exit 1; }

LINK="vless://${UUID}@${DOMAIN}:${PORT}?type=tcp&security=reality&pbk=${PUB}&fp=${FINGERPRINT}&sni=${DOMAIN}&sid=${SID}&flow=xtls-rprx-vision&encryption=none#RealitySmokeTest"

echo
echo "================= ПАРАМЕТРЫ ==================="
echo "IP:          ${IP}"
echo "DOMAIN/SNI:  ${DOMAIN}"
echo "Reality TCP: ${PORT}"
echo "Dest HTTPS:  ${DEST_PORT}"
echo "Fingerprint: ${FINGERPRINT}"
echo
echo "================= ССЫЛКА VLESS ================="
echo "$LINK"
echo
echo "===================== QR ======================="
qrencode -t ansiutf8 "$LINK"
echo
echo "Импортируй ссылку/QR в Happ/V2RayTun, включи мобильный интернет и открой ya.ru"
