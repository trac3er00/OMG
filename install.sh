#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SCRIPT="$SCRIPT_DIR/OAL-setup.sh"

echo "[DEPRECATED] install.sh is deprecated. Use OAL-setup.sh instead." >&2

exec bash "$SETUP_SCRIPT" "$@"
