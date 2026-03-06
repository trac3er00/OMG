#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OMG_ROOT="$(dirname "$PLUGIN_DIR")"

echo "Updating OMG Bun plugin..."
exec bash "$OMG_ROOT/OMG-setup.sh" update --install-as-plugin --non-interactive
