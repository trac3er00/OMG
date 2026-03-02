#!/bin/bash
# OAL Plugin Update Script
# This script is called by Claude Code when user clicks "Update" in /plugin

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warning() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
PLUGIN_CACHE_DIR="$CLAUDE_DIR/plugins/cache/oh-advanced-layer/oal"

# Find the plugin source directory
# Priority: 1) git repo if exists, 2) plugin cache, 3) current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OAL_ROOT="$(dirname "$PLUGIN_DIR")"

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                               ║${NC}"
echo -e "${BLUE}║              OAL Plugin Updater v1.0.0                       ║${NC}"
echo -e "${BLUE}║                                                               ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Detect if this is a git-based (dev) install or a copy-based install
detect_install_type() {
    # Check if the installed files are symlinks (dev mode)
    if [ -L "$CLAUDE_DIR/commands/OAL:init.md" ] 2>/dev/null || \
       [ -L "$CLAUDE_DIR/hooks/session-start.py" ] 2>/dev/null || \
       [ -d "$OAL_ROOT/.git" ] 2>/dev/null; then
        echo "symlink"
    else
        echo "copy"
    fi
}

INSTALL_TYPE=$(detect_install_type)

if [ "$INSTALL_TYPE" = "symlink" ]; then
    info "Detected development mode (symlinked installation)"
    echo ""
    
    # Check if we're in a git repo
    if [ -d "$OAL_ROOT/.git" ]; then
        info "Git repository detected at: $OAL_ROOT"
        cd "$OAL_ROOT"
        
        # Check for uncommitted changes
        if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
            warning "You have uncommitted changes in the repository"
            echo ""
            read -p "Stash changes and continue? (y/n) [y]: " STASH_CHANGES
            STASH_CHANGES=${STASH_CHANGES:-y}
            if [ "$STASH_CHANGES" = "y" ]; then
                git stash push -m "Auto-stash before OAL update"
                success "Changes stashed"
            else
                error "Update cancelled - uncommitted changes present"
                exit 1
            fi
        fi
        
        # Pull latest changes
        info "Pulling latest changes from git..."
        if git pull; then
            success "Repository updated to latest"
            echo ""
            success "OAL is now up to date! (symlinks automatically reflect changes)"
        else
            error "Failed to pull from git repository"
            exit 1
        fi
    else
        info "Symlinked installation detected but no git repository found"
        info "Source directory: $OAL_ROOT"
        warning "Please manually update the source files"
    fi
else
    info "Detected standard installation (copy mode)"
    echo ""
    
    # Find OAL-setup.sh
    SETUP_SCRIPT=""
    if [ -f "$OAL_ROOT/OAL-setup.sh" ]; then
        SETUP_SCRIPT="$OAL_ROOT/OAL-setup.sh"
    elif [ -f "$PLUGIN_CACHE_DIR/OAL-setup.sh" ]; then
        SETUP_SCRIPT="$PLUGIN_CACHE_DIR/OAL-setup.sh"
    else
        # Try to find it in common locations
        for path in "$HOME/oal" "$HOME/OAL" "$HOME/projects/oal" "$HOME/code/oal"; do
            if [ -f "$path/OAL-setup.sh" ]; then
                SETUP_SCRIPT="$path/OAL-setup.sh"
                break
            fi
        done
    fi
    
    if [ -n "$SETUP_SCRIPT" ]; then
        info "Found OAL-setup.sh at: $SETUP_SCRIPT"
        echo ""
        info "Running update via OAL-setup.sh..."
        echo ""
        
        # Run the setup script in update mode
        if bash "$SETUP_SCRIPT" update; then
            echo ""
            success "OAL updated successfully!"
        else
            error "Update failed"
            exit 1
        fi
    else
        error "Could not find OAL-setup.sh"
        error "Please manually run: ./OAL-setup.sh update"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Update complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
info "What's next:"
echo "  • Restart Claude Code to load any new commands/agents"
echo "  • Run /OAL:health-check to verify the installation"
echo ""