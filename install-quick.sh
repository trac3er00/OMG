#!/bin/bash
# OMG Quick Installer Delegate
# Usage: curl -sL https://raw.githubusercontent.com/oh-my-openagent/OMG/main/install-quick.sh | bash
# Or:    ./install-quick.sh [init flags]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

preflight() {
  log_info "Running pre-flight checks..."

  if ! command -v node >/dev/null 2>&1; then
    log_error "Node.js 18+ not found. Install from https://nodejs.org"
    exit 1
  fi

  local node_ver
  node_ver=$(node -p "process.versions.node")
  local node_major
  node_major=$(node -p "process.versions.node.split('.')[0]")
  if [[ "$node_major" -lt 18 ]]; then
    log_error "Node.js $node_ver not supported. OMG requires Node.js 18+"
    exit 1
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    log_error "Python 3.10+ not found. Install from https://python.org"
    exit 1
  fi

  local py_ver
  py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  local py_maj py_min
  py_maj=$(printf '%s' "$py_ver" | cut -d. -f1)
  py_min=$(printf '%s' "$py_ver" | cut -d. -f2)
  if [[ "$py_maj" -lt 3 ]] || { [[ "$py_maj" -eq 3 ]] && [[ "$py_min" -lt 10 ]]; }; then
    log_error "Python $py_ver not supported. OMG requires Python 3.10+"
    exit 1
  fi

  if ! command -v npx >/dev/null 2>&1; then
    log_error "npx not found. Install npm (bundled with Node.js)."
    exit 1
  fi

  log_success "Node.js $node_ver and Python $py_ver detected"
}

main() {
  if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    echo "OMG Quick Installer"
    echo ""
    echo "Usage: $0 [INIT_OPTIONS]"
    echo ""
    echo "Delegates to: npx @trac3r/oh-my-god init"
    exit 0
  fi

  preflight
  log_info "Delegating to OMG init wizard..."
  exec npx @trac3r/oh-my-god init "$@"
}

main "$@"
