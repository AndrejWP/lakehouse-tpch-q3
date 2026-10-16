#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose run --rm --no-deps catalog-init python scripts/bootstrap.py --catalog-only
docker compose run --rm --no-deps runner python scripts/bootstrap.py
