#!/usr/bin/env bash
# Run linting and type-checking for both backend and frontend.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== backend: ruff =="
(cd backend && uv run ruff check .)

echo "== backend: mypy =="
(cd backend && uv run mypy src)

echo "== frontend: eslint =="
(cd frontend && npm run lint)

echo "== frontend: tsc =="
(cd frontend && npm run typecheck)
