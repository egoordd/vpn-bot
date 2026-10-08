#!/usr/bin/env bash
# Корпоративный финский узел: marzban-node + nginx для Reality + сетевой экран.
#
# Повторяет рабочую схему польского узла (docs/NODE_AMSTERDAM.md): панель на
# 23.95.3.18 раздаёт узлу xray-конфиг, а Reality каждого узла «прячется» за
# собственным nginx на :8443 с настоящим сертификатом Let's Encrypt для
# <IP>.sslip.io (SNI обязан резолвиться в IP узла — см. feedback_reality_sni_ip_fix).
#
# Запуск (сертификат панели — на stdin):
#   ssh root@<IP> 'bash -s -- <IP> "<порты через запятую>"' < setup_node.sh
# Скрипт повторяемый: второй прогон ничего не ломает.
set -euo pipefail
# Вызывающий может прийти с umask 077 (так безопаснее доставлять сертификат) —
# тогда webroot certbot'а получался 700 и nginx отвечал Let's Encrypt 403.
umask 022

IP="$1"
PORTS="$2"
DOM="$IP.sslip.io"
PANEL_IP="23.95.3.18"
export DEBIAN_FRONTEND=noninteractive

CERT="$(cat)"
[ -n "$CERT" ] || { echo "нет сертификата панели на stdin"; exit 1; }

echo "== $IP: вход только по ключу"
# sshd берёт ПЕРВОЕ встреченное значение, а файлы sshd_config.d читает по
# алфавиту: «99-…» проигрывал облачному 50-cloud-init.conf с
# PasswordAuthentication yes (08.10.2026, новый немецкий сервер). Поэтому 01-.
rm -f /etc/ssh/sshd_config.d/99-keyonly.conf
cat > /etc/ssh/sshd_config.d/01-keyonly.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl reload ssh
sshd -T | grep -q '^passwordauthentication no$' || { echo "вход по паролю НЕ отключился"; exit 1; }

echo "== $IP: пакеты"
apt-get -o DPkg::Lock::Timeout=1800 update -qq
apt-get -o DPkg::Lock::Timeout=1800 install -y -qq docker.io docker-compose-v2 nginx certbot ufw unattended-upgrades >/dev/null
systemctl enable --now docker >/dev/null 2>&1

if ! swapon --show | grep -q .; then
  echo "== $IP: swap 1 ГБ"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== $IP: nginx и сертификат для $DOM"
mkdir -p /var/www/letsencrypt
chmod -R a+rX /var/www/letsencrypt
cat > /etc/nginx/sites-available/acme <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 404; }
}
EOF
rm -f /etc/nginx/sites-enabled/default
ln -sf ../sites-available/acme /etc/nginx/sites-enabled/acme
nginx -t -q && systemctl reload nginx
if [ ! -f "/etc/letsencrypt/live/$DOM/fullchain.pem" ]; then
  certbot certonly --webroot -w /var/www/letsencrypt -d "$DOM" --non-interactive --agree-tos \
    --register-unsafely-without-email --deploy-hook "systemctl reload nginx" -q
fi
cat > /etc/nginx/sites-available/reality-front <<EOF
server {
    listen 8443 ssl http2;
    listen [::]:8443 ssl http2;
    server_name $DOM;
    ssl_certificate /etc/letsencrypt/live/$DOM/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOM/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    location / { default_type text/plain; return 200 "ok\n"; }
}
EOF
ln -sf ../sites-available/reality-front /etc/nginx/sites-enabled/reality-front
nginx -t -q && systemctl reload nginx

echo "== $IP: marzban-node"
mkdir -p /opt/marzban-node /var/lib/marzban-node
umask 077
printf '%s\n' "$CERT" > /var/lib/marzban-node/ssl_client_cert.pem
umask 022
cat > /opt/marzban-node/docker-compose.yml <<'EOF'
services:
  marzban-node:
    image: gozargah/marzban-node:latest
    restart: always
    network_mode: host
    environment:
      SSL_CLIENT_CERT_FILE: "/var/lib/marzban-node/ssl_client_cert.pem"
      SERVICE_PORT: "62050"
      XRAY_API_PORT: "62051"
    volumes:
      - /var/lib/marzban-node:/var/lib/marzban-node
EOF
(cd /opt/marzban-node && docker compose pull -q && docker compose up -d)

echo "== $IP: сетевой экран"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
for port in 22 80 8443; do ufw allow "$port/tcp" >/dev/null; done
for port in ${PORTS//,/ }; do ufw allow "$port/tcp" >/dev/null; done
for port in 62050 62051; do ufw allow from "$PANEL_IP" to any port "$port" proto tcp >/dev/null; done
ufw --force enable >/dev/null

echo "== $IP: готово"
docker ps --format '  {{.Image}} {{.Status}}'
curl -sk --max-time 5 -o /dev/null -w "  nginx :8443 → HTTP %{http_code}\n" --resolve "$DOM:8443:127.0.0.1" "https://$DOM:8443/"
