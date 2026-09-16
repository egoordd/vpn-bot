#!/usr/bin/env bash
# Выложить визитку unlock-project.site на российский сервер сайта.
#
# Визитка — статика: папка landing/ как есть, без сборки. Файлы распаковываются
# во временную папку и подменяют рабочую одним переименованием, поэтому обрыв
# SSH посередине не оставит людям полупустую страницу. Предыдущая версия лежит
# рядом в .old — откат одним mv.
#
# Конфигурация nginx и выпуск сертификата — в deploy/landing/unlock-project.conf.
#
#   scripts/deploy_landing.sh
set -euo pipefail

HOST="root@168.113.210.6"
KEY="$HOME/.ssh/ruweb"
HERE="$(cd "$(dirname "$0")/../landing" && pwd)"

echo "→ файлы визитки на сервер"
tar -C "$HERE" --no-xattrs --no-mac-metadata -czf - index.html og.png fonts \
  | ssh -i "$KEY" -o BatchMode=yes "$HOST" 'bash -c "
set -e
D=/var/www/unlock-project.site
rm -rf \$D.new && mkdir -p \$D.new && tar -xzf - -C \$D.new
test -s \$D.new/index.html && test -s \$D.new/og.png && test -d \$D.new/fonts
chmod -R a+rX \$D.new
rm -rf \$D.old
[ -d \$D ] && mv \$D \$D.old
mv \$D.new \$D
"'

echo "→ проверка снаружи"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://unlock-project.site/)
echo "  https://unlock-project.site → HTTP $code"
[ "$code" = "200" ]
