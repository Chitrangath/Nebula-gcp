#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

printf '%s\n' "The legacy Fly.io deployment path was removed because it is not permanently free."
printf '%s\n' "Starting the reviewed OCI Always Free owner wizard instead."
exec "$SCRIPT_DIR/be002_production_auth_wizard.sh"
