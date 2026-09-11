#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <path-to-backup-file>" >&2
  exit 2
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 2
fi

echo "Restoring PostgreSQL database 'barq_tasks' from ${BACKUP_FILE}..."
docker compose cp "$BACKUP_FILE" postgres:/tmp/restore.dump
docker compose exec -T postgres pg_restore -U barq_app -d barq_tasks --clean --if-exists /tmp/restore.dump
docker compose exec -T postgres rm /tmp/restore.dump

echo "Restore complete. Verifying records..."
curl -s http://localhost:8080/records