#!/bin/bash
# Индивидуальная подписка на своих серверах клиента: служба работает, пока
# действует ссылка. Раз в 5 минут (ind-guard.timer) спрашиваем у шлюза подписок
# срок — заголовок subscription-userinfo — и после него гасим службу; продлили
# ссылку в реестре шлюза — поднимаем обратно.
#
# Ошибка сети, ответ не 200 или без срока — ничего не меняем: недоступность
# шлюза не повод отключать оплаченный VPN.
#
# /etc/xray-individual/guard.env (или файл из первого аргумента — когда на
# одной машине несколько индивидуальных ссылок, у каждой своя служба и свой
# таймер, например ind-guard-ind2.timer с /etc/xray-ind2/guard.env):
#   SUB_URL=https://unlockru.site/sub/<токен>
#   SERVICE=xray-individual            # на релеях: xray-individual-relay
set -u
. "${1:-/etc/xray-individual/guard.env}"

response=$(curl -s -m 20 -A "unlock-ind-guard/1" -o /dev/null -D - -w 'HTTP_CODE:%{http_code}\n' "$SUB_URL") || exit 0
code=$(printf '%s\n' "$response" | sed -n 's/^HTTP_CODE://p')
[ "$code" = "200" ] || exit 0
expire=$(printf '%s\n' "$response" | tr -d '\r' | grep -i '^subscription-userinfo:' | grep -o 'expire=[0-9]*' | cut -d= -f2)
[ -n "$expire" ] || exit 0

if [ "$expire" -ne 0 ] && [ "$expire" -le "$(date +%s)" ]; then
    if systemctl is-active --quiet "$SERVICE"; then
        systemctl stop "$SERVICE"
        logger -t ind-guard "срок вышел $(date -u -d "@$expire" '+%F %T UTC') — $SERVICE остановлен"
    fi
elif ! systemctl is-active --quiet "$SERVICE"; then
    systemctl start "$SERVICE"
    until="бессрочно"
    [ "$expire" -ne 0 ] && until="до $(date -u -d "@$expire" '+%F %T UTC')"
    logger -t ind-guard "ссылка действует $until — $SERVICE запущен"
fi
