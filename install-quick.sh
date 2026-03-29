#!/bin/bash
# OMG One-Click Installer
# Usage: curl -sL https://raw.githubusercontent.com/oh-my-openagent/OMG/main/install-quick.sh | bash
# Or:    ./install-quick.sh [--source /path/to/OMG]

set -euo pipefail

VERSION="2.3.0"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
INSTALL_SOURCE=""
AUTO_DETECT_AGENTS=true
SKIP_PROMPTS=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source)
                INSTALL_SOURCE="$2"
                shift 2
                ;;
            --no-detect)
                AUTO_DETECT_AGENTS=false
                shift
                ;;
            --yes|-y)
                SKIP_PROMPTS=true
                shift
                ;;
            --help|-h)
                echo "OMG One-Click Installer"
                echo ""
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --source PATH    Install from local source (for development)"
                echo "  --no-detect      Skip automatic agent detection"
                echo "  --yes, -y        Skip all prompts (CI mode)"
                echo "  --help, -h       Show this help"
                echo ""
                echo "One-liner (curl):"
                echo "  curl -sL https://raw.githubusercontent.com/oh-my-openagent/OMG/main/install-quick.sh | bash"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    if [[ ! -t 0 ]] || [[ "$SKIP_PROMPTS" == "true" ]]; then
        SKIP_PROMPTS=true
    fi
}

# Pre-flight checks
preflight() {
    log_info "Running pre-flight checks..."

    # Python check
    if ! command -v python3 &>/dev/null; then
        log_error "Python 3.10+ not found. Install from https://python.org"
        exit 1
    fi

    local py_ver
    py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local py_maj py_min
    py_maj=$(echo "$py_ver" | cut -d. -f1)
    py_min=$(echo "$py_ver" | cut -d. -f2)

    if [[ "$py_maj" -lt 3 ]] || { [[ "$py_maj" -eq 3 ]] && [[ "$py_min" -lt 10 ]]; }; then
        log_error "Python $py_ver not supported. OMG requires Python 3.10+"
        exit 1
    fi

    log_success "Python $py_ver detected"
}

# Detect available agents
detect_agents() {
    log_info "Detecting available AI agents..."

    local detected=()

    # Claude Code
    if command -v claude &>/dev/null; then
        detected+=("Claude Code")
    fi

    # Codex
    if command -v codex &>/dev/null; then
        detected+=("Codex")
    fi

    # Gemini CLI
    if command -v gemini &>/dev/null; then
        detected+=("Gemini CLI")
    fi

    # OpenCode
    if command -v opencode &>/dev/null; then
        detected+=("OpenCode")
    fi

    # Kimi CLI
    if command -v kimi &>/dev/null; then
        detected+=("Kimi CLI")
    fi

    # Cursor (check common paths)
    if [[ -x "/Applications/Cursor.app/Contents/MacOS/Cursor" ]] || \
       command -v cursor &>/dev/null; then
        detected+=("Cursor")
    fi

    if [[ ${#detected[@]} -eq 0 ]]; then
        log_warn "No AI agents detected. Install Claude Code for best experience:"
        log_warn "  https://claude.com/claude-code"
        echo ""
    else
        log_success "Detected: ${detected[*]}"
    fi

    echo "$detected"
}

# Auto-select preset based on detected agents
select_preset() {
    local detected=("$@")

    if [[ ${#detected[@]} -eq 0 ]]; then
        echo "safe"
        return
    fi

    local has_codex=false
    local has_gemini=false
    local has_claude=false

    for agent in "${detected[@]}"; do
        case "$agent" in
            Codex) has_codex=true ;;
            "Gemini CLI") has_gemini=true ;;
            "Claude Code") has_claude=true ;;
        esac
    done

    if $has_codex && $has_gemini; then
        echo "production"
    elif $has_codex || $has_gemini; then
        echo "balanced"
    else
        echo "safe"
    fi
}

# Perform installation
do_install() {
    local source_path="$1"
    local preset="$2"

    log_info "Installing OMG v$VERSION (preset: $preset)..."

    # Use OMG-setup.sh
    local setup_script="$source_path/OMG-setup.sh"

    if [[ ! -f "$setup_script" ]]; then
        log_error "Setup script not found at $setup_script"
        exit 1
    fi

    if [[ -n "$INSTALL_SOURCE" ]]; then
        log_info "Installing from local source: $source_path"
        bash "$setup_script" install \
            --preset="$preset" \
            --mode=omg-only \
            --non-interactive \
            --install-as-plugin
    else
        log_error "Remote install not yet implemented. Use --source or clone repository."
        exit 1
    fi

    log_success "Installation complete!"
}

# Verify installation
verify_install() {
    log_info "Verifying installation..."

    # Check for installed markers
    local installed=false

    if [[ -f "$CLAUDE_DIR/hooks/.omg-version" ]] || \
       [[ -d "$CLAUDE_DIR/omg-runtime" ]]; then
        installed=true
    fi

    if $installed; then
        log_success "OMG is installed!"
        echo ""
        echo "Next steps:"
        echo "  1. Run 'omg status' to check installation status"
        echo "  2. Run 'npx omg init --auto' to initialize (optional)"
        echo ""
        return 0
    else
        log_warn "Installation verification pending. Check manually:"
        echo "  omg status"
        return 1
    fi
}

# Main
main() {
    parse_args "$@"

    echo "=========================================="
    echo "  OMG One-Click Installer v$VERSION"
    echo "=========================================="
    echo ""

    # Determine source
    local source_path
    if [[ -n "$INSTALL_SOURCE" ]]; then
        source_path="$INSTALL_SOURCE"
    else
        # Try to find local OMG
        local script_dir
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        if [[ -f "$script_dir/OMG-setup.sh" ]]; then
            source_path="$script_dir"
        fi
    fi

    if [[ -z "$source_path" ]]; then
        log_error "No OMG source found. Use --source or run from OMG directory."
        exit 1
    fi

    preflight

    # Detect agents
    local -a detected_agents=()
    if $AUTO_DETECT_AGENTS; then
        mapfile -t detected_agents < <(detect_agents)
    fi

    # Select preset
    local preset
    preset=$(select_preset "${detected_agents[@]}")

    if ! $SKIP_PROMPTS; then
        echo ""
        echo "Detected agents: ${detected_agents[*]:-none}"
        echo "Selected preset:  $preset"
        echo ""
        read -p "Continue with installation? [Y/n] " -r
        if [[ "${REPLY:-}" =~ ^[Nn] ]]; then
            echo "Installation cancelled."
            exit 0
        fi
    fi

    do_install "$source_path" "$preset"
    verify_install
}

main "$@"
