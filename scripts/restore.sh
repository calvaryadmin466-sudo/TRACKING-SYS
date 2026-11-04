#!/usr/bin/env bash
# Restore a PostgreSQL backup produced by backup.sh. DESTRUCTIVE: it overwrites
# the target database. Requires explicit confirmation.
#
# Usage: DATABASE_URL=postgres://user:pass@host:5432/db ./scripts/restore.sh <dump.sql.gz>
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL}"
DUMP="${1:?usage: restore.sh <dump.sql.gz>}"
[ -f "$DUMP" ] || { echo "no such file: $DUMP" >&2; exit 1; }

echo "!! This will RESTORE into: $DATABASE_URL"
echo "!! Existing data in that database may be overwritten."
read -r -p "Type 'yes' to continue: " ans
[ "$ans" = "yes" ] || { echo "aborted."; exit 1; }

echo ">> ensuring PostGIS extension"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS postgis;"
echo ">> restoring $DUMP"
gunzip -c "$DUMP" | psql "$DATABASE_URL" -v ON_ERROR_STOP=1
echo "restore complete."
