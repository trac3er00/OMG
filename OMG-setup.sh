#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
ACTION="install"
ACTION_EXPLICIT=false
DRY_RUN=false
NON_INTERACTIVE=false
MERGE_POLICY="ask"
FRESH_INSTALL=false
INSTALL_AS_PLUGIN=false
USE_SYMLINK=false
SKIP_CODEX_SKILLS=false
MANIFEST_PATH="$CLAUDE_DIR/.omg-manifest"
PLUGIN_CACHE_DIR="$CLAUDE_DIR/plugins/cache/oh-advanced-layer/omg"
PLUGIN_MARKER="$PLUGIN_CACHE_DIR/.omg-plugin-bundle"
VERSION=""
TMP_MANIFEST=()

usage() {
  cat <<'EOF'
OMG Setup Manager

Usage:
  ./OMG-setup.sh <action> [options]
  ./OMG-setup.sh [options]

Actions:
  install      Install or update OMG
  update       Alias of install
  reinstall    Uninstall then install
  uninstall    Remove OMG-managed files

Options:
  --fresh
  --symlink
  --install-as-plugin
  --skip-codex-skills
  --dry-run
  --non-interactive
  --merge-policy=ask|apply|skip
  -h, --help
EOF
}

say() {
  printf '%s\n' "$*"
}

record_manifest() {
  TMP_MANIFEST+=("$1")
}

run_or_echo() {
  if $DRY_RUN; then
    say "DRY RUN: $*"
    return 0
  fi
  "$@"
}

copy_file() {
  local src="$1"
  local dst="$2"
  local mode="${3:-644}"
  if $DRY_RUN; then
    say "DRY RUN: install $src -> $dst"
    record_manifest "$dst"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  if $USE_SYMLINK; then
    ln -sfn "$src" "$dst"
  else
    cp "$src" "$dst"
  fi
  chmod "$mode" "$dst"
  record_manifest "$dst"
}

copy_dir_glob() {
  local src_dir="$1"
  local pattern="$2"
  local dst_dir="$3"
  local mode="${4:-644}"
  shopt -s nullglob
  for src in "$src_dir"/$pattern; do
    [ -e "$src" ] || continue
    copy_file "$src" "$dst_dir/$(basename "$src")" "$mode"
  done
  shopt -u nullglob
}

copy_tree() {
  local src_dir="$1"
  local dst_dir="$2"
  local selector="${3:-all}"
  while IFS= read -r src; do
    case "$selector" in
      markdown)
        [[ "$src" == *.md ]] || continue
        ;;
      ts-only)
        [[ "$src" == *.ts ]] || continue
        ;;
      runtime)
        [[ "$src" == *.ts || "$src" == *.json || "$src" == *.sh ]] || continue
        ;;
      all)
        ;;
      *)
        ;;
    esac
    local rel="${src#$src_dir/}"
    local mode=644
    case "$src" in
      *.sh|*.ts|*.mjs) mode=755 ;;
    esac
    copy_file "$src" "$dst_dir/$rel" "$mode"
  done < <(find "$src_dir" -type f | sort)
}

is_standalone_installed() {
  [ -f "$MANIFEST_PATH" ] || [ -d "$CLAUDE_DIR/omg-runtime" ]
}

is_plugin_installed() {
  [ -f "$PLUGIN_MARKER" ]
}

prompt_start_action() {
  if $ACTION_EXPLICIT || $NON_INTERACTIVE || $DRY_RUN; then
    return 0
  fi

  local standalone_installed=false
  local plugin_installed=false
  is_standalone_installed && standalone_installed=true
  is_plugin_installed && plugin_installed=true

  say ""
  say "Select OMG setup action:"
  say "  1. Install standalone"
  if $standalone_installed; then
    say "  2. Update standalone"
  fi
  say "  3. Install as plugin"
  if $plugin_installed; then
    say "  4. Update plugin install"
  fi
  say "  5. Uninstall"
  say "  0. Cancel"
  say ""
  read -r -p "Choose [1/2/3/4/5/0]: " choice
  case "${choice:-}" in
    1) ACTION="install"; INSTALL_AS_PLUGIN=false ;;
    2) ACTION="update"; INSTALL_AS_PLUGIN=false ;;
    3) ACTION="install"; INSTALL_AS_PLUGIN=true ;;
    4) ACTION="update"; INSTALL_AS_PLUGIN=true ;;
    5) ACTION="uninstall" ;;
    0) say "Cancelled by user."; exit 0 ;;
    *) say "Invalid selection."; exit 1 ;;
  esac
}

parse_args() {
  if [ $# -gt 0 ]; then
    case "$1" in
      install|update|reinstall|uninstall)
        ACTION="$1"
        ACTION_EXPLICIT=true
        shift
        ;;
      -h|--help|help)
        usage
        exit 0
        ;;
    esac
  fi

  for arg in "$@"; do
    case "$arg" in
      --dry-run) DRY_RUN=true ;;
      --symlink) USE_SYMLINK=true ;;
      --non-interactive) NON_INTERACTIVE=true ;;
      --fresh) FRESH_INSTALL=true ;;
      --install-as-plugin) INSTALL_AS_PLUGIN=true ;;
      --skip-codex-skills) SKIP_CODEX_SKILLS=true ;;
      --merge-policy=*) MERGE_POLICY="${arg#*=}" ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        say "Unknown option: $arg"
        usage
        exit 1
        ;;
    esac
  done

  if [ "$ACTION" = "reinstall" ]; then
    FRESH_INSTALL=true
    ACTION="install"
  fi

  if [ ! -t 0 ] || [ -n "${npm_execpath:-}" ] || [ -n "${npm_lifecycle_event:-}" ]; then
    NON_INTERACTIVE=true
  fi

  if [ -n "${npm_execpath:-}" ] || [ -n "${npm_lifecycle_event:-}" ]; then
    INSTALL_AS_PLUGIN=true
  fi
}

preflight() {
  say "═══════════════════════════════════════════════════════════════"
  say "  OMG Setup Manager — $ACTION"
  say "═══════════════════════════════════════════════════════════════"
  say ""
  say "Pre-flight checks..."
  if ! command -v bun >/dev/null 2>&1; then
    say "  ✗ bun not found. Install Bun first: https://bun.sh"
    exit 1
  fi
  VERSION="$(bun -e 'import { readFileSync } from "node:fs"; console.log(JSON.parse(readFileSync(process.argv[1], "utf8")).version);' "$SCRIPT_DIR/package.json")"
  say "  ✓ Bun $(bun --version)"
}

backup_existing() {
  local backup_dir="$CLAUDE_DIR/.omg-backup-$(date +%Y%m%d_%H%M%S)"
  if $DRY_RUN; then
    say "  DRY RUN: backup -> $backup_dir"
    return 0
  fi
  mkdir -p "$backup_dir"
  for path in settings.json commands agents hooks omg-runtime rules templates; do
    if [ -e "$CLAUDE_DIR/$path" ]; then
      cp -R "$CLAUDE_DIR/$path" "$backup_dir/" 2>/dev/null || true
    fi
  done
  say "  ✓ Backup: $backup_dir"
}

remove_manifest_paths() {
  if [ ! -f "$MANIFEST_PATH" ]; then
    return 0
  fi
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    if $DRY_RUN; then
      say "DRY RUN: remove $path"
    else
      rm -rf "$path"
    fi
  done < "$MANIFEST_PATH"
  if ! $DRY_RUN; then
    rm -f "$MANIFEST_PATH"
  fi
}

remove_legacy_runtime_files() {
  local legacy_ext="py"
  local dirs=(
    "$CLAUDE_DIR/hooks"
    "$CLAUDE_DIR/omg-runtime/scripts"
    "$CLAUDE_DIR/omg-runtime/runtime"
    "$CLAUDE_DIR/omg-runtime/tools"
    "$CLAUDE_DIR/omg-runtime/control_plane"
    "$CLAUDE_DIR/omg-runtime/lab"
    "$CLAUDE_DIR/omg-runtime/omg_natives"
    "$CLAUDE_DIR/omg-runtime/registry"
  )
  local dir
  local file
  for dir in "${dirs[@]}"; do
    [ -d "$dir" ] || continue
    while IFS= read -r file; do
      if $DRY_RUN; then
        say "DRY RUN: remove legacy $file"
      else
        rm -f "$file"
      fi
    done < <(find "$dir" -maxdepth 1 -type f -name "*.${legacy_ext}" | sort)
  done
}

merge_settings() {
  local source="$SCRIPT_DIR/settings.json"
  local target="$CLAUDE_DIR/settings.json"

  if [ ! -f "$target" ]; then
    copy_file "$source" "$target" 644
    return 0
  fi

  case "$MERGE_POLICY" in
    skip)
      say "  ~ Settings merge skipped"
      return 0
      ;;
    apply)
      ;;
    ask)
      if $NON_INTERACTIVE; then
        :
      else
        read -r -p "Apply settings merge? [Y/n]: " reply
        case "${reply:-Y}" in
          n|N) say "  ~ Settings merge skipped"; return 0 ;;
        esac
      fi
      ;;
    *)
      say "Invalid merge policy: $MERGE_POLICY"
      exit 1
      ;;
  esac

  if $DRY_RUN; then
    say "DRY RUN: merge settings $target <= $source"
  else
    bun "$SCRIPT_DIR/scripts/settings-merge.ts" "$target" "$source"
    say "  ✓ Settings merged (auto)"
  fi
  record_manifest "$target"
}

write_manifest() {
  if $DRY_RUN; then
    return 0
  fi
  printf '%s\n' "${TMP_MANIFEST[@]}" | awk 'NF' | sort -u > "$MANIFEST_PATH"
}

install_plugin_bundle() {
  say "  Plugin bundle mode enabled: install plugin + MCP + HUD together"
  if ! $DRY_RUN; then
    mkdir -p "$PLUGIN_CACHE_DIR"
  fi
  copy_tree "$SCRIPT_DIR/.claude-plugin" "$PLUGIN_CACHE_DIR/.claude-plugin" ""
  copy_file "$SCRIPT_DIR/.mcp.json" "$PLUGIN_CACHE_DIR/.mcp.json" 644
  copy_tree "$SCRIPT_DIR/hud" "$PLUGIN_CACHE_DIR/hud" ""
  if $DRY_RUN; then
    say "DRY RUN: write $PLUGIN_MARKER"
  else
    printf '%s\n' "omg-plugin-bundle-v2" > "$PLUGIN_MARKER"
  fi
  record_manifest "$PLUGIN_CACHE_DIR"
}

install_runtime() {
  say "Step 1/4: Install core runtime..."
  copy_tree "$SCRIPT_DIR/commands" "$CLAUDE_DIR/commands" "markdown"
  copy_tree "$SCRIPT_DIR/agents" "$CLAUDE_DIR/agents" "markdown"
  copy_tree "$SCRIPT_DIR/rules" "$CLAUDE_DIR/rules" "markdown"
  copy_tree "$SCRIPT_DIR/templates" "$CLAUDE_DIR/templates/omg" "all"
  copy_tree "$SCRIPT_DIR/hooks" "$CLAUDE_DIR/hooks" "ts-only"
  copy_tree "$SCRIPT_DIR/runtime" "$CLAUDE_DIR/omg-runtime/runtime" "runtime"
  copy_tree "$SCRIPT_DIR/scripts" "$CLAUDE_DIR/omg-runtime/scripts" "runtime"
  copy_tree "$SCRIPT_DIR/tools" "$CLAUDE_DIR/omg-runtime/tools" "runtime"
  copy_tree "$SCRIPT_DIR/control_plane" "$CLAUDE_DIR/omg-runtime/control_plane" "runtime"
  copy_tree "$SCRIPT_DIR/lab" "$CLAUDE_DIR/omg-runtime/lab" "runtime"
  copy_tree "$SCRIPT_DIR/registry" "$CLAUDE_DIR/omg-runtime/registry" "runtime"
  copy_tree "$SCRIPT_DIR/omg_natives" "$CLAUDE_DIR/omg-runtime/omg_natives" "runtime"
  copy_tree "$SCRIPT_DIR/hud" "$CLAUDE_DIR/omg-runtime/hud" "all"
  copy_file "$SCRIPT_DIR/.mcp.json" "$CLAUDE_DIR/omg-runtime/.mcp.json" 644
  copy_file "$SCRIPT_DIR/package.json" "$CLAUDE_DIR/omg-runtime/package.json" 644
  copy_file "$SCRIPT_DIR/tsconfig.json" "$CLAUDE_DIR/omg-runtime/tsconfig.json" 644
  copy_file "$SCRIPT_DIR/bunfig.toml" "$CLAUDE_DIR/omg-runtime/bunfig.toml" 644
}

install_action() {
  if $FRESH_INSTALL; then
    uninstall_action
  fi
  backup_existing
  remove_legacy_runtime_files
  install_runtime
  say "Step 2/4: Merge settings and templates..."
  merge_settings
  say "Step 3/4: Install portable runtime metadata..."
  if ! $DRY_RUN; then
    mkdir -p "$CLAUDE_DIR/hooks" "$CLAUDE_DIR/omg-runtime"
    mkdir -p "$CLAUDE_DIR/omg-runtime"
    printf '%s\n' "omg-v2-$VERSION" > "$CLAUDE_DIR/hooks/.omg-version"
  fi
  record_manifest "$CLAUDE_DIR/omg-runtime"
  record_manifest "$CLAUDE_DIR/hooks/.omg-version"
  if $INSTALL_AS_PLUGIN; then
    say "Step 4/4: Install plugin bundle..."
    install_plugin_bundle
  else
    say "Step 4/4: Plugin bundle skipped"
  fi
  write_manifest
  say ""
  say "═══════════════════════════════════════════════════════════════"
  say "  ✅ OMG Bun install completed successfully"
  say "═══════════════════════════════════════════════════════════════"
}

uninstall_action() {
  say "Uninstalling OMG Bun runtime..."
  remove_manifest_paths
  if $DRY_RUN; then
    say "DRY RUN: remove $PLUGIN_CACHE_DIR"
  else
    rm -rf "$PLUGIN_CACHE_DIR"
    rm -rf "$CLAUDE_DIR/omg-runtime"
    rm -f "$CLAUDE_DIR/hooks/.omg-version"
  fi
  say "  ✓ Uninstall complete"
}

main() {
  parse_args "$@"
  prompt_start_action
  preflight
  case "$ACTION" in
    install|update) install_action ;;
    uninstall) uninstall_action ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
