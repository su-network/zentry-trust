#!/usr/bin/env bash
set -euo pipefail

# Step 2 enrollment helper for Docker Compose quickstart:
# - takes existing *.jwt enrollment tokens on the host
# - runs `ziti edge enroll` inside the quickstart container (no local `ziti` needed)
# - copies the resulting *.json identities back to the host
#
# Usage:
#   export ZITI_COMPOSE_FILE='./zentry-trust/compose.yml'
#   ./scripts/ziti_step2_enroll_quickstart.sh ZentrySentinel.jwt ZentrySentinel.json
#   ./scripts/ziti_step2_enroll_quickstart.sh ZentryClient.jwt ZentryClient.json
#
# Defaults:
#   OUT_DIR=.

ZITI_COMPOSE_FILE=${ZITI_COMPOSE_FILE:-./zentry-trust/compose.yml}
OUT_DIR=${OUT_DIR:-.}

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <input.jwt> <output.json>" >&2
  exit 2
fi

JWT_PATH=$1
OUT_NAME=$2

if [[ ! -f "$JWT_PATH" ]]; then
  echo "ERROR: JWT not found: $JWT_PATH" >&2
  exit 2
fi

if [[ ! -f "$ZITI_COMPOSE_FILE" ]]; then
  echo "ERROR: compose file not found: $ZITI_COMPOSE_FILE" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

jwt_base=$(basename "$JWT_PATH")
out_base=$(basename "$OUT_NAME")

container_jwt="/tmp/${jwt_base}"
container_json="/tmp/${out_base}"

# Copy JWT into container

docker compose -f "$ZITI_COMPOSE_FILE" cp "$JWT_PATH" "quickstart:$container_jwt"

# Enroll inside container

docker compose -f "$ZITI_COMPOSE_FILE" exec -T quickstart ziti edge enroll --jwt "$container_jwt" --out "$container_json"

# Copy identity JSON back out

docker compose -f "$ZITI_COMPOSE_FILE" cp "quickstart:$container_json" "$OUT_DIR/$out_base"

# Cleanup in container (best-effort)
docker compose -f "$ZITI_COMPOSE_FILE" exec -T quickstart rm -f "$container_jwt" "$container_json" >/dev/null 2>&1 || true

echo "Enrolled identity written to: $OUT_DIR/$out_base"
