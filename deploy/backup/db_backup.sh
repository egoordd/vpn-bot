#!/usr/bin/env bash
# Daily Postgres backup on the bot VPS. Dumps each configured database from its
# running container, gzips atomically, keeps the newest $KEEP per database, and
# optionally mirrors to an offsite target.
#
# Covers every control-plane store:
#   - vpn_bot     (the Telegram bot: users, subscriptions, payments, wallet, funnel)
#   - marzban     (the LIVE panel: every client's UUID, inbounds, hosts, nodes)
#   - remnawave   (dormant since 2026-07-12; dumped only while its container runs)
#
# Marzban was added on 2026-08-02 after a gap: the panel moved onto this box on
# 08-01 and Remnawave was stopped to free memory, so the 08-02 run saved the bot
# database and nothing else. The panel holds the only copy of each client's VPN
# identity — losing it breaks every installed config at once — so it is now
# backed up first and its failure is loud.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/vpnbot}"
KEEP="${KEEP:-14}"
MARZBAN_DB="${MARZBAN_DB:-/var/lib/marzban/db.sqlite3}"
# Config worth keeping beside the database: without xray_config.json the
# inbounds (and their Reality keys) would have to be rebuilt by hand, and every
# existing client link would stop matching the server.
MARZBAN_EXTRA="${MARZBAN_EXTRA:-/var/lib/marzban/xray_config.json /opt/marzban/.env /opt/marzban/docker-compose.yml}"

# Optional offsite mirror. Set OFFSITE_DEST to an rsync target (e.g.
# user@host:/path or an rclone remote handled by a wrapper) to enable. Left
# empty = local-only (no offsite).
OFFSITE_DEST="${OFFSITE_DEST:-}"

mkdir -p "$BACKUP_DIR"
ts=$(date +%Y%m%d_%H%M%S)

# dump_db <prefix> <container> <pg_user> <pg_db>
dump_db() {
  local prefix="$1" container="$2" user="$3" db="$4"
  local out="$BACKUP_DIR/${prefix}_${ts}.sql.gz"
  local tmp="${out}.tmp"

  if ! docker ps --format '{{.Names}}' | grep -qx "$container"; then
    echo "skip $prefix: container '$container' not running" >&2
    return 0
  fi

  # PGPASSWORD is read from the container's own env, so no secret is passed here.
  if docker exec "$container" sh -c \
      "PGPASSWORD=\"\${POSTGRES_PASSWORD:-}\" pg_dump -U '$user' -d '$db' --no-owner --clean --if-exists" \
      | gzip >"$tmp"; then
    mv "$tmp" "$out"
    ls -1t "$BACKUP_DIR/${prefix}"_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
    echo "backup ok: $out ($(du -h "$out" | cut -f1)); kept $(ls -1 "$BACKUP_DIR/${prefix}"_*.sql.gz | wc -l) files"
  else
    rm -f "$tmp"
    echo "backup FAILED: $prefix" >&2
    return 1
  fi
}

# dump_marzban — snapshot of the panel's SQLite database plus its config.
dump_marzban() {
  if [ ! -f "$MARZBAN_DB" ]; then
    # Only a problem if the panel is actually here; on a node it never is.
    if docker ps --format '{{.Names}}' | grep -qx marzban; then
      echo "backup FAILED: marzban is running but no database at $MARZBAN_DB" >&2
      return 1
    fi
    echo "skip marzban: no database at $MARZBAN_DB" >&2
    return 0
  fi

  local out="$BACKUP_DIR/marzban_${ts}.sqlite3.gz"
  local snap="$BACKUP_DIR/.marzban_${ts}.snap"

  # sqlite3's online backup rather than cp: the panel writes continuously, and a
  # plain copy can capture a file mid-transaction that restores into a corrupt
  # panel — the kind of backup you only discover is worthless when you need it.
  # The integrity check runs on the copy, so a bad snapshot fails here and not
  # during a restore.
  if ! python3 - "$MARZBAN_DB" "$snap" <<'PY'
import sqlite3, sys

source, target = sys.argv[1], sys.argv[2]
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
    if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("integrity check failed on the snapshot")
PY
  then
    rm -f "$snap"
    echo "backup FAILED: marzban database snapshot" >&2
    return 1
  fi

  gzip -c "$snap" >"${out}.tmp" && mv "${out}.tmp" "$out"
  rm -f "$snap"
  { ls -1t "$BACKUP_DIR"/marzban_*.sqlite3.gz 2>/dev/null || true; } | tail -n +$((KEEP + 1)) | xargs -r rm -f
  echo "backup ok: $out ($(du -h "$out" | cut -f1))"

  local conf="$BACKUP_DIR/marzban_conf_${ts}.tar.gz"
  local present=()
  for path in $MARZBAN_EXTRA; do
    if [ -e "$path" ]; then present+=("$path"); fi
  done
  # The panel is a hand-started `docker run` — no compose file, no unit — so the
  # image, host networking and mounts live nowhere but the running container.
  # Without this, a restore has the data and no way to know how to serve it.
  local spec="$BACKUP_DIR/.marzban_container.json"
  if docker inspect marzban >"$spec" 2>/dev/null; then
    present+=("$spec")
  else
    rm -f "$spec"
  fi
  if [ ${#present[@]} -gt 0 ]; then
    tar czf "${conf}.tmp" "${present[@]}" 2>/dev/null && mv "${conf}.tmp" "$conf"
    { ls -1t "$BACKUP_DIR"/marzban_conf_*.tar.gz 2>/dev/null || true; } | tail -n +$((KEEP + 1)) | xargs -r rm -f
    echo "backup ok: $conf"
  fi
  rm -f "$spec"
}

# alert — say it out loud. A backup that quietly stopped working is the same
# failure mode as a node quietly leaving the subscription: nobody notices until
# the day it matters. Uses the ops alerts bot, never the customer-facing one.
alert() {
  local token="${ALERTS_BOT_TOKEN:-}" chat="${ALERTS_CHAT_ID:-}"
  [ -n "$token" ] && [ -n "$chat" ] || return 0
  curl -s -m 15 -o /dev/null \
    --data-urlencode "chat_id=${chat}" \
    --data-urlencode "text=$1" \
    "https://api.telegram.org/bot${token}/sendMessage" || true
}

rc=0
dump_marzban || rc=1
dump_db vpn_bot "${CONTAINER:-vpn-bot-postgres-1}" "${DB_USER:-vpn_bot}" "${DB_NAME:-vpn_bot}" || rc=1
dump_db remnawave "${RW_CONTAINER:-remnawave-db}" "${RW_DB_USER:-postgres}" "${RW_DB_NAME:-postgres}" || rc=1

if [ -n "$OFFSITE_DEST" ]; then
  if rsync -az --delete "$BACKUP_DIR"/ "$OFFSITE_DEST"/; then
    echo "offsite mirror ok -> $OFFSITE_DEST"
  else
    echo "offsite mirror FAILED -> $OFFSITE_DEST" >&2
    rc=1
  fi
fi

if [ "$rc" -ne 0 ]; then
  alert "⚠️ Бэкап не прошёл полностью ($(date '+%d.%m %H:%M')). Смотреть: journalctl -u vpnbot-backup"
fi

exit "$rc"
