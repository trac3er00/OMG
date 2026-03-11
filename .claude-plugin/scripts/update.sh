#!/bin/bash
# OMG Plugin Update Script
# Simplified version for Claude Code plugin system

set -e

echo "Updating OMG plugin..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OMG_ROOT="$(dirname "$PLUGIN_DIR")"
PKG_NAME="@trac3er/oh-my-god"
CURRENT_VERSION=""
LATEST_VERSION=""
TMP_DIR=""

cleanup() {
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
}
trap cleanup EXIT

if [ -f "$OMG_ROOT/.claude-plugin/plugin.json" ]; then
    CURRENT_VERSION="$(python3 - "$OMG_ROOT/.claude-plugin/plugin.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding='utf-8'))
except Exception:
    print("")
    raise SystemExit(0)

version = data.get('version') if isinstance(data, dict) else ''
print(str(version).strip() if version is not None else '')
PY
)"
fi

if command -v npm >/dev/null 2>&1; then
    LATEST_VERSION="$(npm view "$PKG_NAME" version --silent 2>/dev/null | tr -d '[:space:]')"
fi

if [ -n "$LATEST_VERSION" ] && [ "$LATEST_VERSION" != "$CURRENT_VERSION" ]; then
    echo "Found newer npm release: ${CURRENT_VERSION:-unknown} -> $LATEST_VERSION"
    TMP_DIR="$(mktemp -d)"
    npm install --prefix "$TMP_DIR" "$PKG_NAME@$LATEST_VERSION" --silent --no-audit --no-fund

    UPDATE_ROOT="$TMP_DIR/node_modules/@trac3er/oh-my-god"
    if [ -f "$UPDATE_ROOT/OMG-setup.sh" ]; then
        echo "Running update from npm release package..."
        bash "$UPDATE_ROOT/OMG-setup.sh" update --install-as-plugin --non-interactive
        echo ""
        echo "✓ OMG updated successfully"
        echo "  Restart Claude Code if you see new commands"
        exit 0
    fi

    echo "ERROR: npm package missing OMG-setup.sh"
    exit 1
fi

if [ -n "$LATEST_VERSION" ]; then
    echo "Already on latest npm release: $LATEST_VERSION"
else
    echo "Could not determine latest npm release; using local update path"
fi

if [ -d "$OMG_ROOT/.git" ]; then
    echo "Found git repository at: $OMG_ROOT"
    cd "$OMG_ROOT"
    
    # Check for local changes
    STASHED=false
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo "Stashing local changes..."
        if git stash push -m "Auto-stash before update"; then
            STASHED=true
        fi
    fi
    
    # Pull latest
    echo "Pulling latest changes..."
    git pull origin main
    
    # Restore stashed changes
    if $STASHED; then
        echo "Restoring stashed changes..."
        git stash pop || echo "Warning: Could not restore stashed changes. Run 'git stash pop' manually."
    fi

    if [ -f "$OMG_ROOT/OMG-setup.sh" ]; then
        echo "Running OMG-setup.sh update (plugin bundle mode)..."
        bash "$OMG_ROOT/OMG-setup.sh" update --install-as-plugin --non-interactive
    else
        echo "ERROR: Could not find OMG-setup.sh"
        exit 1
    fi
else
    if [ -f "$OMG_ROOT/OMG-setup.sh" ]; then
        echo "Running OMG-setup.sh update..."
        bash "$OMG_ROOT/OMG-setup.sh" update --install-as-plugin --non-interactive
    else
        echo "ERROR: Could not find OMG-setup.sh"
        exit 1
    fi
fi

echo ""
echo "✓ OMG updated successfully"
echo "  Restart Claude Code if you see new commands"
