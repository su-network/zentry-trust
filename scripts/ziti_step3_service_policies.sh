#!/usr/bin/env bash
set -euo pipefail

# Creates a demo echo service and the minimum policies so:
# - ZentrySentinel can BIND (host) the service
# - ZentryClient can DIAL (connect) the service
# - Both identities can use any edge router ("#all")
# - The service can use any edge router ("#all")
#
# Usage:
#   # Option A: use locally installed `ziti` CLI
#   export ZITI_CTRL="https://<controller-ip-or-dns>:1280"
#   export ZITI_PWD="<admin-password>"
#   ./scripts/ziti_step3_service_policies.sh
#
#   # Option B: use Docker Compose quickstart (no local `ziti` required)
#   export ZITI_PWD="<admin-password>"
#   export ZITI_COMPOSE_FILE="./zentry-trust/compose.yml"
#   ./scripts/ziti_step3_service_policies.sh

: "${ZITI_PWD:?set ZITI_PWD (admin password)}"

ZITI_USER=${ZITI_USER:-admin}
ZITI_INSECURE=${ZITI_INSECURE:-1} # 1 => pass -y to accept self-signed certs
ZITI_CA_FILE=${ZITI_CA_FILE:-}
ZITI_COMPOSE_FILE=${ZITI_COMPOSE_FILE:-}

_have_cmd() { command -v "$1" >/dev/null 2>&1; }

_ziti() {
	# Prefer local ziti; else use docker compose exec if compose file provided.
	if _have_cmd ziti; then
		ziti "$@"
		return
	fi

	if [[ -n "$ZITI_COMPOSE_FILE" ]]; then
		docker compose -f "$ZITI_COMPOSE_FILE" exec -T quickstart ziti "$@"
		return
	fi

	echo "ERROR: 'ziti' CLI not found. Install it, or set ZITI_COMPOSE_FILE to your quickstart compose.yml (e.g. ./zentry-trust/compose.yml)." >&2
	exit 127
}

if [[ -z "${ZITI_CTRL:-}" ]]; then
	# When using compose exec, the controller is reachable as localhost inside the container.
	ZITI_CTRL="https://localhost:1280"
fi

SERVICE_NAME=${SERVICE_NAME:-ZentryWeb}
SENTINEL_NAME=${SENTINEL_NAME:-ZentrySentinel}
CLIENT_NAME=${CLIENT_NAME:-ZentryClient}

login_args=("$ZITI_CTRL" -u "$ZITI_USER" -p "$ZITI_PWD")
if [[ "$ZITI_INSECURE" == "1" ]]; then
	login_args+=(-y)
fi
if [[ -n "$ZITI_CA_FILE" ]]; then
	login_args+=(--ca "$ZITI_CA_FILE")
fi

if ! _ziti edge login "${login_args[@]}"; then
	cat >&2 <<EOF

ERROR: login failed.

If you're using Docker Compose quickstart, note that the admin password is stored in the quickstart volume.
Changing ZITI_PWD after the first boot will NOT update the existing controller.

To reset quickstart and start fresh (DELETES the quickstart volume):
	docker compose -f "${ZITI_COMPOSE_FILE:-./zentry-trust/compose.yml}" down -v
	export ZITI_PWD='<admin-password>'
	docker compose -f "${ZITI_COMPOSE_FILE:-./zentry-trust/compose.yml}" up -d

Then rerun this script.
EOF
	exit 1
fi

# Create the service
_ziti edge create service "$SERVICE_NAME"

# Allow hosting and dialing
_ziti edge create service-policy "${SERVICE_NAME}-bind" Bind --service-roles "@${SERVICE_NAME}" --identity-roles "@${SENTINEL_NAME}"
_ziti edge create service-policy "${SERVICE_NAME}-dial" Dial --service-roles "@${SERVICE_NAME}" --identity-roles "@${CLIENT_NAME}"

# Allow identities to use routers; and allow the service on routers.
# In a lab, "#all" is simplest; tighten these roles later.
_ziti edge create edge-router-policy "${SERVICE_NAME}-identities" --edge-router-roles "#all" --identity-roles "@${SENTINEL_NAME},@${CLIENT_NAME}"
_ziti edge create service-edge-router-policy "${SERVICE_NAME}-service" --edge-router-roles "#all" --service-roles "@${SERVICE_NAME}"

echo "Created service and policies for service: ${SERVICE_NAME}"