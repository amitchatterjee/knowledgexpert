#!/usr/bin/env bash
set -euo pipefail

# Wrapper for docker compose that sets COMPOSE_PROFILES based on
# KNOWLEDGEXPERT_ENV. When KNOWLEDGEXPERT_ENV=dev, the "dev" profile
# will be enabled (so services with profiles: ["dev"] will start).
# Usage: ./compose.sh up -d

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

# Export COMPOSE_PROFILES from KNOWLEDGEXPERT_ENV, defaulting to 'dev'.
# Append any existing COMPOSE_PROFILES so future additional profiles are preserved.
export COMPOSE_PROFILES="${KNOWLEDGEXPERT_ENV:-dev}${COMPOSE_PROFILES:+,${COMPOSE_PROFILES}}"

# Forward all arguments to docker compose
docker compose -f "$COMPOSE_FILE" "$@"
