#!/usr/bin/env bash
# Apply database migrations against DATABASE_URL (see .env).
set -euo pipefail

cd "$(dirname "$0")/../backend"

uv run alembic upgrade head
