#!/usr/bin/env bash
# Daily Postgres backup of the bot DB on the VPS. Dumps from the running
# container, gzips, keeps the newest $KEEP, writes atomically.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/vpnbot}"
KEEP="${KEEP:-14}"
CONTAINER="${CONTAINER:-vpn-bot-postgres-1}"
DB_USER="${DB_USER:-vpn_bot}"
DB_NAME="${DB_NAME:-vpn_bot}"

mkdir -p "$BACKUP_DIR"
ts=$(date +%Y%m%d_%H%M%S)
out="$BACKUP_DIR/vpn_bot_${ts}.sql.gz"
tmp="${out}.tmp"
trap 'rm -f "$tmp"' EXIT

docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --clean --if-exists | gzip >"$tmp"
mv "$tmp" "$out"

ls -1t "$BACKUP_DIR"/vpn_bot_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "backup ok: $out ($(du -h "$out" | cut -f1)); kept $(ls -1 "$BACKUP_DIR"/vpn_bot_*.sql.gz | wc -l) files"
