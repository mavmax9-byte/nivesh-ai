#!/usr/bin/env bash
# Run backend unit tests and, if requested, end-to-end tests.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== backend: pytest =="
(cd backend && uv run pytest)

if [ "${1:-}" = "--e2e" ]; then
  echo "== e2e: playwright =="
  npx playwright test
fi
