#!/usr/bin/env bash
# Apply SQL migrations in order. The compose Postgres only runs /migrations on the
# FIRST initialisation of an empty data volume; use this to apply new migrations
# (e.g. 0002_stage3) to an existing database.
#
# Usage: DATABASE_URL=postgres://user:pass@host:5432/db ./scripts/migrate.sh
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL (postgres://user:pass@host:5432/db)}"
DIR="$(cd "$(dirname "$0")/../migrations" && pwd)"

shopt -s nullglob
for f in "$DIR"/*.up.sql; do
  echo ">> applying $(basename "$f")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done
echo "migrations applied."
