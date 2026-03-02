#!/bin/bash
# OAL Plugin Install Script
# This script is called by Claude Code when user installs the plugin

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warning() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                               ║${NC}"
echo -e "${BLUE}║              OAL Plugin Installer v1.0.0                     ║${NC}"
echo -e "${BLUE}║                                                               ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OAL_ROOT="$(dirname "$PLUGIN_DIR")"

# Check if OAL-setup.sh exists
if [ -f "$OAL_ROOT/OAL-setup.sh" ]; then
    info "Found OAL-setup.sh, running installation..."
    echo ""
    bash "$OAL_ROOT/OAL-setup.sh" install
else
    error "OAL-setup.sh not found at: $OAL_ROOT/OAL-setup.sh"
    error "Plugin installation requires the OAL setup script"
    exit 1
fi

echo ""
success "OAL Plugin installed successfully!"
echo ""
info "Getting started:"
echo "  1. Run /OAL:init to initialize a project"
echo "  2. Run /OAL:health-check to verify everything works"
echo "  3. Try /OAL:escalate codex 'your task' for multi-agent help"
echo ""