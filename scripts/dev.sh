#!/usr/bin/env bash
# Start the full local development stack.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found -- copying .env.example. Review it before continuing."
  cp .env.example .env
fi

docker compose up --build
