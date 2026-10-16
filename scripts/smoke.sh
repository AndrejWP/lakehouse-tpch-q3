#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose ps --format json > evidence/compose-status.json
python3 scripts/check_services.py evidence/compose-status.json
docker compose run --rm --no-deps minio-init 'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc ls --recursive --json local/lakehouse' > evidence/minio-objects.ndjson
docker compose run --rm --no-deps runner python scripts/smoke.py
