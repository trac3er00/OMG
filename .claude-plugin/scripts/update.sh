#!/bin/bash
# OAL Plugin Update Script
# Simplified version for Claude Code plugin system

set -e

echo "Updating OAL plugin..."

# Find OAL root - prioritize git repo if we're in one
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OAL_ROOT="$(dirname "$PLUGIN_DIR")"

# Check if running from source git repo
if [ -d "$OAL_ROOT/.git" ]; then
    echo "Found git repository at: $OAL_ROOT"
    cd "$OAL_ROOT"
    
    # Check for local changes
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo "Stashing local changes..."
        git stash push -m "Auto-stash before update" || true
    fi
    
    # Pull latest
    echo "Pulling latest changes..."
    git pull origin main
    echo "Update complete!"
    echo ""
    echo "Note: Changes are immediately active (symlinked installation)"
else
    # Running from cache - run OAL-setup.sh
    if [ -f "$OAL_ROOT/OAL-setup.sh" ]; then
        echo "Running OAL-setup.sh update..."
        bash "$OAL_ROOT/OAL-setup.sh" update
    else
        echo "ERROR: Could not find OAL-setup.sh"
        exit 1
    fi
fi

echo ""
echo "✓ OAL updated successfully"
echo "  Restart Claude Code if you see new commands"
