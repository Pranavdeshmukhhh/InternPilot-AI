#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
command -v docker >/dev/null || { echo 'Install Docker Engine/Desktop with Compose v2 first.' >&2; exit 1; }
docker info --format '{{.ServerVersion}}' >/dev/null
docker compose version >/dev/null
python3 scripts/setup_env.py
docker compose config --quiet
if [[ "${1:-}" != "--no-start" ]]; then
  docker compose up --build --detach --wait --wait-timeout 300
fi
