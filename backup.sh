#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="./backups"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_FILE="${BACKUP_DIR}/barq_tasks_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "Backing up PostgreSQL database 'barq_tasks' to ${BACKUP_FILE}..."
docker compose exec -T postgres pg_dump -U barq_app -d barq_tasks -F c -f /tmp/backup.dump
docker compose cp postgres:/tmp/backup.dump "$BACKUP_FILE"
docker compose exec -T postgres rm /tmp/backup.dump

echo "Backup complete: ${BACKUP_FILE}"
ls -la "$BACKUP_FILE"