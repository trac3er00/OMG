#!/bin/bash
# OMG Plugin Uninstall Script
# This script is called by Claude Code when user uninstalls the plugin

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
echo -e "${BLUE}║              OMG Plugin Uninstaller v2.0.9                   ║${NC}"
echo -e "${BLUE}║                                                               ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
OMG_ROOT="$(dirname "$PLUGIN_DIR")"

# Check if OMG-setup.sh exists
if [ -f "$OMG_ROOT/OMG-setup.sh" ]; then
    info "Running uninstall via OMG-setup.sh..."
    echo ""
    bash "$OMG_ROOT/OMG-setup.sh" uninstall --non-interactive
else
    warning "OMG-setup.sh not found, performing manual cleanup..."
    
    CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    
    # Remove OMG files manually
    rm -f "$CLAUDE_DIR"/commands/OMG:*.md 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/agents/omg-*.md 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/.omg-version 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/session-start.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/session-end-capture.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/prompt-enhancer.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/circuit-breaker.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/test-validator.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/firewall.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/secret-guard.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/tool-ledger.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/post-write.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/quality-runner.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/stop-gate.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/stop_dispatcher.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/pre-compact.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/pre-tool-inject.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/post-tool-failure.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/config-guard.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/policy_engine.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/trust_review.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/shadow_manager.py 2>/dev/null || true
    rm -rf "$CLAUDE_DIR"/hooks/__pycache__ 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/_common.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/_budget.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/_memory.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/_learnings.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/_agent_registry.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/state_migration.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/hooks/fetch-rate-limits.py 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/.omg-manifest 2>/dev/null || true
    rm -rf "$CLAUDE_DIR"/omg-runtime 2>/dev/null || true
    rm -rf "$CLAUDE_DIR"/templates/omg 2>/dev/null || true
    rm -f "$CLAUDE_DIR"/rules/0[0-4]-*.md 2>/dev/null || true
fi

echo ""
success "OMG Plugin uninstalled successfully!"
echo ""
