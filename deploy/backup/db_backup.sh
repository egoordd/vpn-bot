#!/usr/bin/env bash
# Daily Postgres backup on the bot VPS. Dumps each configured database from its
# running container, gzips atomically, keeps the newest $KEEP per database, and
# optionally mirrors to an offsite target.
#
# Covers BOTH control-plane databases:
#   - vpn_bot     (the Telegram bot: users, subscriptions, payments, wallet, funnel)
#   - remnawave   (the panel: panel users, inbounds, hosts, nodes) — critical since
#                 the Marzban→Remnawave cutover moved all VPN state here.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/vpnbot}"
KEEP="${KEEP:-14}"

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

rc=0
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

exit "$rc"
