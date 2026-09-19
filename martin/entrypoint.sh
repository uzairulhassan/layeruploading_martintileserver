#!/bin/sh
# Lean Martin runtime config for cost-efficient VPS hosting (Martin v0.18.x keys).
# Env overrides (optional):
#   MARTIN_DATABASE_URL
#   MARTIN_CACHE_MB       (default 64; was ~512)
#   MARTIN_POOL_SIZE      (default 5; was 20)
#   MARTIN_WORKERS        (default 2; was often 8)
set -eu

CONN="${MARTIN_DATABASE_URL:-postgresql://gis_user:gis_password@db:5432/gis_app}"
CACHE_MB="${MARTIN_CACHE_MB:-64}"
POOL="${MARTIN_POOL_SIZE:-5}"
WORKERS="${MARTIN_WORKERS:-2}"
CONFIG="/tmp/martin-runtime.yaml"

cat > "$CONFIG" <<EOF
listen_addresses: "0.0.0.0:3000"
# Fewer workers = less RAM/CPU on small droplets
worker_processes: ${WORKERS}
# Tile cache (MB). 0 disables. Default Martin is 512.
cache_size_mb: ${CACHE_MB}
preferred_encoding: gzip
web_ui: disable

postgres:
  connection_string: "${CONN}"
  pool_size: ${POOL}
  # Bounds for map fitBounds come from Django LayerInfo
  auto_bounds: skip
  auto_publish:
    from_schemas:
      - layers_data
    tables:
      source_id_format: "{table}"
EOF

exec martin --config "$CONFIG"
