#!/usr/bin/env bash
set -euo pipefail

# Step 2 (from scratch) for the Docker Compose quickstart in this repo:
# - starts the quickstart if needed
# - logs into the controller
# - creates Sentinel + Client identities
# - outputs/copies the enrollment JWTs to the current directory
#
# Usage:
#   export ZITI_PWD='<admin-password>'
#   export ZITI_COMPOSE_FILE='./zentry-trust/compose.yml'
#   ./scripts/ziti_step2_identities_quickstart.sh

: "${ZITI_PWD:?set ZITI_PWD (admin password)}"

ZITI_COMPOSE_FILE=${ZITI_COMPOSE_FILE:-./zentry-trust/compose.yml}
ZITI_USER=${ZITI_USER:-admin}
ZITI_INSECURE=${ZITI_INSECURE:-1}
ZITI_CA_FILE=${ZITI_CA_FILE:-}

# Ensure the controller advertises an address reachable by whatever will enroll/use identities.
# For local dev this should be localhost; for a VPS it should be the public IP/DNS.
export ZITI_CTRL_ADVERTISED_ADDRESS=${ZITI_CTRL_ADVERTISED_ADDRESS:-localhost}
export ZITI_ROUTER_ADVERTISED_ADDRESS=${ZITI_ROUTER_ADVERTISED_ADDRESS:-$ZITI_CTRL_ADVERTISED_ADDRESS}

SENTINEL_NAME=${SENTINEL_NAME:-ZentrySentinel}
CLIENT_NAME=${CLIENT_NAME:-ZentryClient}

OUT_DIR=${OUT_DIR:-.}
ZITI_RESET=${ZITI_RESET:-0} # 1 => docker compose down -v before starting

if [[ ! -f "$ZITI_COMPOSE_FILE" ]]; then
  echo "ERROR: compose file not found: $ZITI_COMPOSE_FILE" >&2
  exit 2
fi

if [[ "$ZITI_RESET" == "1" ]]; then
  echo "[step2] resetting quickstart state (docker compose down -v)"
  docker compose -f "$ZITI_COMPOSE_FILE" down -v
fi

echo "[step2] starting quickstart (docker compose)"
docker compose -f "$ZITI_COMPOSE_FILE" up -d

echo "[step2] waiting for quickstart to be healthy"
# quickstart has a healthcheck; poll it.
for _ in $(seq 1 60); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose -f "$ZITI_COMPOSE_FILE" ps -q quickstart)" 2>/dev/null || true)
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  sleep 2
done

if [[ "$status" != "healthy" ]]; then
  echo "ERROR: quickstart container did not become healthy. Check logs:" >&2
  echo "  docker compose -f $ZITI_COMPOSE_FILE logs --tail=200 quickstart" >&2
  exit 1
fi

ZITI_CTRL=${ZITI_CTRL:-https://localhost:1280}

login_args=("$ZITI_CTRL" -u "$ZITI_USER" -p "$ZITI_PWD")
if [[ "$ZITI_INSECURE" == "1" ]]; then
  login_args+=(-y)
fi
if [[ -n "$ZITI_CA_FILE" ]]; then
  login_args+=(--ca "$ZITI_CA_FILE")
fi

echo "[step2] logging in to controller as $ZITI_USER"
if ! docker compose -f "$ZITI_COMPOSE_FILE" exec -T quickstart ziti edge login "${login_args[@]}"; then
  cat >&2 <<EOF

ERROR: login failed.

Common causes:
- Wrong admin password (quickstart stores state in a volume; changing ZITI_PWD later doesn't change it).
- You previously ran quickstart with a different password.

To start from scratch, rerun with:
  export ZITI_RESET=1

Then rerun this script.
EOF
  exit 1
fi

sentinel_jwt_in_container="/home/ziggy/${SENTINEL_NAME}.jwt"
client_jwt_in_container="/home/ziggy/${CLIENT_NAME}.jwt"

echo "[step2] creating identity: $SENTINEL_NAME (role: zentry.sentinel)"
docker compose -f "$ZITI_COMPOSE_FILE" exec -T quickstart ziti edge create identity "$SENTINEL_NAME" -a zentry.sentinel -o "$sentinel_jwt_in_container"

echo "[step2] creating identity: $CLIENT_NAME (role: zentry.client)"
docker compose -f "$ZITI_COMPOSE_FILE" exec -T quickstart ziti edge create identity "$CLIENT_NAME" -a zentry.client -o "$client_jwt_in_container"

mkdir -p "$OUT_DIR"

echo "[step2] copying JWTs to $OUT_DIR"
docker compose -f "$ZITI_COMPOSE_FILE" cp "quickstart:$sentinel_jwt_in_container" "$OUT_DIR/${SENTINEL_NAME}.jwt"
docker compose -f "$ZITI_COMPOSE_FILE" cp "quickstart:$client_jwt_in_container" "$OUT_DIR/${CLIENT_NAME}.jwt"

echo "[step2] done"
echo "- Sentinel JWT: $OUT_DIR/${SENTINEL_NAME}.jwt"
echo "- Client JWT:   $OUT_DIR/${CLIENT_NAME}.jwt"
echo
echo "Next: enroll each JWT on its target device:"
echo "  ziti edge enroll --jwt ${SENTINEL_NAME}.jwt --out ${SENTINEL_NAME}.json"
echo "  ziti edge enroll --jwt ${CLIENT_NAME}.jwt --out ${CLIENT_NAME}.json"
