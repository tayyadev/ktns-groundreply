#!/bin/sh
# Produces a LOCAL backup. Send it to independently encrypted offsite storage immediately.
set -eu
MODE="${1:-production}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
NOW=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$BACKUP_DIR/groundreply-$NOW.sql.gz"
if [ "$MODE" = "production" ]; then
  docker compose --env-file .env -f deploy/compose.prod.yml exec -T db \
    pg_dump -U groundreply -d groundreply --no-owner | gzip -9 > "$OUT"
else
  docker compose exec -T db pg_dump -U groundreply -d groundreply --no-owner | gzip -9 > "$OUT"
fi
chmod 600 "$OUT"
echo "Backup written to $OUT; verify restore and copy to secure offsite storage."
