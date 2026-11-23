#!/usr/bin/env bash
# Production deploy for GeoLayers on the VPS.
# GitHub Actions and SSH fallback both run:
#   cd /path/to/layeruploading_martintileserver && ./scripts/deploy.sh
#
# Set SKIP_GIT_PULL=1 when the caller already updated the working tree
# (the Actions workflow pulls before invoking this script).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.prod.yml)

echo "==> Deploying GeoLayers from $(pwd)"

if [[ "${SKIP_GIT_PULL:-}" != "1" ]]; then
  echo "==> Fetching origin/main"
  git fetch origin main
  git checkout main
  git pull --ff-only origin main
fi

SHA="$(git rev-parse --short HEAD)"
echo "==> Rebuilding at ${SHA}"
"${COMPOSE[@]}" up -d --build

echo "==> Waiting for geolayers_web"
web_up=0
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx web; then
    web_up=1
    break
  fi
  sleep 2
done
"${COMPOSE[@]}" ps
if [[ "$web_up" -ne 1 ]]; then
  echo "ERROR: service web is not running" >&2
  "${COMPOSE[@]}" logs --tail=80 web || true
  exit 1
fi

echo "==> Smoke check :8081"
ok=0
for _ in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8081/ || true)"
  if [[ "$code" != "000" && "$code" != "" ]]; then
    echo "    HTTP ${code}"
    ok=1
    break
  fi
  sleep 2
done

if [[ "$ok" -ne 1 ]]; then
  echo "ERROR: GeoLayers did not respond on http://127.0.0.1:8081/" >&2
  "${COMPOSE[@]}" logs --tail=80 web || true
  exit 1
fi

echo "==> Deployed GeoLayers ${SHA} OK"
