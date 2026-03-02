#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/OAL-setup.sh"

if [ ! -x "$TARGET" ]; then
    echo "Error: $TARGET not found or not executable."
    exit 1
fi

echo "[DEPRECATED] install.sh is deprecated. Use ./OAL-setup.sh <install|update|reinstall|uninstall>."

if [ $# -gt 0 ]; then
    case "$1" in
        install|update|reinstall|uninstall|help|-h|--help)
            exec "$TARGET" "$@"
            ;;
    esac
fi

# Backward-compatible behavior: old install.sh flags map to `install`.
exec "$TARGET" install "$@"
