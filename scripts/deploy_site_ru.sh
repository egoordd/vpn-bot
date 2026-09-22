#!/usr/bin/env bash
# Ship web/ to the Russian VPS that serves unlockproject.site and switch over.
#
# Russian networks block Vercel's addresses and throttle Cloudflare, so the
# live site runs on a domestic server. The build happens there, in a fresh
# directory; the running site is swapped only after the build succeeds, and the
# previous version comes back on its own if the new one does not answer. A
# broken build never takes the site down.
#
#   scripts/deploy_site_ru.sh
set -euo pipefail

HOST="root@168.113.210.6"
KEY="$HOME/.ssh/ruweb"
WEB="$(cd "$(dirname "$0")/../web" && pwd)"

echo "→ исходники на сервер"
tar -C "$WEB" --no-xattrs --no-mac-metadata \
    --exclude=node_modules --exclude=.next --exclude=.vercel \
    --exclude='.env*' --exclude='*.log' -czf - . \
  | ssh -i "$KEY" -o BatchMode=yes "$HOST" \
      'rm -rf /opt/unlock-web/next && mkdir -p /opt/unlock-web/next \
       && tar -xzf - -C /opt/unlock-web/next 2>/dev/null \
       && chown -R unlockweb:unlockweb /opt/unlock-web/next'

echo "→ сборка и переключение"
ssh -i "$KEY" -o BatchMode=yes "$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/unlock-web

run() {
  systemd-run --quiet --wait --pipe --uid=unlockweb --gid=unlockweb \
    -p WorkingDirectory=/opt/unlock-web/next -p EnvironmentFile=/etc/unlock-web.env \
    -p Environment=HOME=/opt/unlock-web -p Environment=PATH=/opt/node/bin:/usr/bin:/bin \
    -p Environment=NODE_OPTIONS=--max-old-space-size=1536 "$@"
}

answers() {
  curl -sf -o /dev/null --retry 20 --retry-delay 1 --retry-connrefused \
    -H "Host: unlockproject.site" http://127.0.0.1:3000/
}

if cmp -s next/package-lock.json app/package-lock.json; then
  # Same lockfile: hard-link the installed packages instead of a fresh install.
  cp -al app/node_modules next/
else
  # NODE_ENV=production в /etc/unlock-web.env: без --include=dev npm ci не ставит
  # typescript, и сборка не находит пути «@/…» из tsconfig.
  run /opt/node/bin/npm ci --include=dev --no-audit --no-fund --loglevel=error
fi

if ! run /opt/node/bin/npm run build >/tmp/unlock-web-build.log 2>&1; then
  tail -30 /tmp/unlock-web-build.log
  echo "СБОРКА НЕ ПРОШЛА — работающий сайт не тронут"
  exit 1
fi

rm -rf prev && mv app prev && mv next app
systemctl restart unlock-web
if answers; then
  echo "ГОТОВО: новая версия отвечает ($(cat app/.next/BUILD_ID))"
else
  echo "Новая версия не отвечает — возвращаю предыдущую"
  rm -rf failed && mv app failed && mv prev app
  systemctl restart unlock-web
  exit 1
fi
REMOTE
