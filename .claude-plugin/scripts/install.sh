#!/bin/bash
# OMG Plugin Install Script
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
echo -e "${BLUE}║              OMG Plugin Installer v2.0.5                     ║${NC}"
echo -e "${BLUE}║                                                               ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OMG_ROOT="$(dirname "$PLUGIN_DIR")"

# Check if OMG-setup.sh exists
if [ -f "$OMG_ROOT/OMG-setup.sh" ]; then
    info "Found OMG-setup.sh, running installation..."
    echo ""
    bash "$OMG_ROOT/OMG-setup.sh" install --install-as-plugin --non-interactive
else
    error "OMG-setup.sh not found at: $OMG_ROOT/OMG-setup.sh"
    error "Plugin installation requires the OMG setup script"
    exit 1
fi

echo ""
success "OMG Plugin installed successfully!"
echo ""
info "Getting started:"
echo "  1. Run /OMG:init to initialize a project"
echo "  2. Run /OMG:health-check to verify everything works"
echo "  3. Try /OMG:escalate codex 'your task' for multi-agent help"
echo ""
