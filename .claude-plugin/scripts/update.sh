#!/bin/bash
# OMG Plugin Update Script
# Simplified version for Claude Code plugin system

set -e

echo "Updating OMG plugin..."

# Find OMG root - prioritize git repo if we're in one
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OMG_ROOT="$(dirname "$PLUGIN_DIR")"

# Check if running from source git repo
if [ -d "$OMG_ROOT/.git" ]; then
    echo "Found git repository at: $OMG_ROOT"
    cd "$OMG_ROOT"
    
    # Check for local changes
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo "Stashing local changes..."
        git stash push -m "Auto-stash before update" || true
    fi
    
    # Pull latest
    echo "Pulling latest changes..."
    git pull origin main

    NEW_VERSION=$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo "")
    if [ -n "$NEW_VERSION" ]; then
        python3 - "$NEW_VERSION" <<'PY'
import json
import sys
from pathlib import Path

new_version = sys.argv[1]
plugin_path = Path('.claude-plugin/plugin.json')
marketplace_path = Path('.claude-plugin/marketplace.json')

plugin = json.loads(plugin_path.read_text(encoding='utf-8'))
plugin['version'] = new_version
plugin_path.write_text(json.dumps(plugin, indent=2) + '\n', encoding='utf-8')

marketplace = json.loads(marketplace_path.read_text(encoding='utf-8'))
marketplace['version'] = new_version
if isinstance(marketplace.get('metadata'), dict):
    marketplace['metadata']['version'] = new_version
plugins = marketplace.get('plugins')
if isinstance(plugins, list) and plugins:
    if isinstance(plugins[0], dict):
        plugins[0]['version'] = new_version
marketplace_path.write_text(json.dumps(marketplace, indent=2) + '\n', encoding='utf-8')
PY
        echo "Synced manifest versions to $NEW_VERSION"
    else
        echo "Skipped manifest version sync (no git tag found)"
    fi

    echo "Update complete!"
    echo ""
    echo "Note: Changes are immediately active (symlinked installation)"
else
    # Running from cache - run OMG-setup.sh
    if [ -f "$OMG_ROOT/OMG-setup.sh" ]; then
        echo "Running OMG-setup.sh update..."
        bash "$OMG_ROOT/OMG-setup.sh" update
    else
        echo "ERROR: Could not find OMG-setup.sh"
        exit 1
    fi
fi

echo ""
echo "✓ OMG updated successfully"
echo "  Restart Claude Code if you see new commands"
