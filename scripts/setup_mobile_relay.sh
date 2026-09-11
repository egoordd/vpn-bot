#!/usr/bin/env bash
# Поднять вход «📶 Мобильный интернет» на сервере в российском облаке.
#
# Зачем: когда оператор опускает мобильный интернет до белого списка, зарубежные
# адреса недоступны целиком. Этот вход стоит на российском адресе и представляется
# разрешённой службой (max.ru), а зарубежный трафик передаёт на наши узлы.
#
# Учётные данные выходов и DNS берутся с работающего московского моста, поэтому
# новый сервер не нужно заводить в панели: он подключается к нашим узлам теми же
# ключами. Ключи самого входа генерируются на нём и никуда не уезжают.
#
#   scripts/setup_mobile_relay.sh 203.0.113.10
#
# Ключ для нового сервера: ~/.ssh/rumobile (или MOBILE_SSH_KEY=…).
set -euo pipefail

TARGET_IP="${1:?укажите IP нового сервера}"
KEY="${MOBILE_SSH_KEY:-$HOME/.ssh/rumobile}"
RELAY_KEY="${RELAY_SSH_KEY:-$HOME/.ssh/runode}"
RELAY="${RELAY_HOST:-root@130.49.143.41}"
SNI="${MOBILE_SNI:-max.ru}"
PORT="${MOBILE_PORT:-443}"
EXITS="${MOBILE_EXITS:-pl,de}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ssh_target() { ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=15 "root@$TARGET_IP" "$@"; }

echo "→ проверяю доступ"
ssh_target 'true'
ssh -i "$RELAY_KEY" -o BatchMode=yes -o ConnectTimeout=15 "$RELAY" 'true'

echo "→ ставлю xray"
ssh_target 'command -v xray >/dev/null || (apt-get update -qq && apt-get install -y -qq curl unzip >/dev/null && bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install >/dev/null); xray version | head -1'

echo "→ ключи входа (генерируются на сервере)"
ssh_target 'xray x25519 > /root/.mobile-keys.txt 2>/dev/null; cat /proc/sys/kernel/random/uuid >> /root/.mobile-keys.txt; openssl rand -hex 8 >> /root/.mobile-keys.txt; chmod 600 /root/.mobile-keys.txt'
ssh_target 'cat /root/.mobile-keys.txt' > "$TMP/keys.txt"
PRIV="$(awk -F': ' '/PrivateKey/{print $2}' "$TMP/keys.txt")"
PUB="$(awk -F': ' '/PublicKey/{print $2}' "$TMP/keys.txt")"
UUID="$(grep -E '^[0-9a-f-]{36}$' "$TMP/keys.txt" | head -1)"
SID="$(grep -E '^[0-9a-f]{16}$' "$TMP/keys.txt" | head -1)"
[ -n "$PRIV" ] && [ -n "$PUB" ] && [ -n "$UUID" ] && [ -n "$SID" ] || { echo "не удалось получить ключи"; exit 1; }

echo "→ собираю конфиг из московского моста"
ssh -i "$RELAY_KEY" -o BatchMode=yes "$RELAY" 'cat /usr/local/etc/xray/config.json' > "$TMP/template.json"
python3 "$HERE/mobile_relay_config.py" --uuid "$UUID" --private-key "$PRIV" --short-id "$SID" \
    --sni "$SNI" --port "$PORT" --exits "$EXITS" < "$TMP/template.json" > "$TMP/config.json"

echo "→ выкладываю (проверка до подмены, как на остальных серверах)"
scp -q -i "$KEY" "$TMP/config.json" "root@$TARGET_IP:/usr/local/etc/xray/config.json.new"
ssh_target "set -e
  [ \"\$(md5sum /usr/local/etc/xray/config.json.new | cut -d' ' -f1)\" = $(md5 -q "$TMP/config.json" 2>/dev/null || md5sum "$TMP/config.json" | cut -d' ' -f1) ]
  xray -test -c /usr/local/etc/xray/config.json.new >/dev/null
  [ -f /usr/local/etc/xray/config.json ] && cp -p /usr/local/etc/xray/config.json /usr/local/etc/xray/config.json.bak-\$(date +%Y%m%d-%H%M%S) || true
  mv /usr/local/etc/xray/config.json.new /usr/local/etc/xray/config.json
  systemctl enable --now xray >/dev/null 2>&1 || systemctl restart xray
  command -v ufw >/dev/null && ufw allow ${PORT}/tcp >/dev/null 2>&1 || true
  sleep 3; systemctl is-active xray"

echo "→ проверяю маскировку: сервер должен отдавать сертификат ${SNI}"
theirs="$(echo | openssl s_client -connect "$TARGET_IP:$PORT" -servername "$SNI" 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || true)"
real="$(echo | openssl s_client -connect "$SNI:443" -servername "$SNI" 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || true)"
echo "   наш вход: ${theirs:-нет ответа}"
echo "   настоящий $SNI: ${real:-нет ответа}"
[ -n "$theirs" ] && [ "$theirs" = "$real" ] && echo "   совпадает — маскировка работает" || echo "   ⚠️ не совпало, разбираться до выдачи людям"

cat <<TXT

Готово. Строки для /etc/unlock-subgw.env на бот-сервере:

MOBILE_HOST=$TARGET_IP
MOBILE_PORT=$PORT
MOBILE_SNI=$SNI
MOBILE_UUID=$UUID
MOBILE_PBK=$PUB
MOBILE_SID=$SID

После этого: systemctl restart unlock-subgw
TXT
