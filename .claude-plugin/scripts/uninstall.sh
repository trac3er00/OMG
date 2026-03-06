#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OMG_ROOT="$(dirname "$PLUGIN_DIR")"

echo "Uninstalling OMG Bun plugin..."
exec bash "$OMG_ROOT/OMG-setup.sh" uninstall --non-interactive
