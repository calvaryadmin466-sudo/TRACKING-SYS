#!/usr/bin/env bash
# Automated PostgreSQL backup with rotation. Run from cron, e.g.:
#   0 2 * * *  DATABASE_URL=... BACKUP_DIR=/var/backups/tracking /opt/app/scripts/backup.sh
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${BACKUP_KEEP:-14}"            # how many dumps to retain
mkdir -p "$BACKUP_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/tracking_${TS}.sql.gz"

echo ">> dumping to $OUT"
# Custom-format would allow parallel restore; plain SQL gz is simplest/portable.
pg_dump "$DATABASE_URL" --no-owner --no-privileges | gzip -9 > "$OUT"
echo ">> size: $(du -h "$OUT" | cut -f1)"

# Rotate: keep the newest $KEEP dumps.
ls -1t "$BACKUP_DIR"/tracking_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  echo ">> pruning $old"
  rm -f "$old"
done
echo "backup complete."
