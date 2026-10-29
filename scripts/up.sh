#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-external}"
if [[ "$mode" != external ]]; then
  printf '%s\n' 'Usage: ./scripts/up.sh [external]' >&2
  exit 2
fi
./scripts/init.sh
python3 scripts/check-mode.py "$mode"
files=(-f compose.yaml -f "compose.${mode}.yaml")
docker compose --env-file .env "${files[@]}" config --quiet
docker compose --env-file .env "${files[@]}" up -d --build --wait api
printf '%s\n' 'Open Legal Services is ready. See APP_PORT in .env for the localhost address.'
