#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BACKUP_TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$CLAUDE_DIR/.omg-backup-$BACKUP_TS"
VERSION="omg-v1-$(date +%Y%m%d)"

PLUGIN_NAME="omg"
PLUGIN_MARKETPLACE="oh-my-god"
LEGACY_PLUGIN_MARKETPLACE="omg"
LEGACY_PLUGIN_MARKETPLACE2="oh-advanced-layer"
LEGACY_PLUGIN_MARKETPLACE3="trac3er"
PLUGIN_REF="${PLUGIN_NAME}@${PLUGIN_MARKETPLACE}"
LEGACY_PLUGIN_REF="${PLUGIN_NAME}@${LEGACY_PLUGIN_MARKETPLACE}"
LEGACY_PLUGIN_REF2="${PLUGIN_NAME}@${LEGACY_PLUGIN_MARKETPLACE2}"
LEGACY_PLUGIN_REF3="${PLUGIN_NAME}@${LEGACY_PLUGIN_MARKETPLACE3}"
PLUGIN_CACHE_DIR="$CLAUDE_DIR/plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME"
LEGACY_PLUGIN_CACHE_DIR="$CLAUDE_DIR/plugins/cache/$LEGACY_PLUGIN_MARKETPLACE/$PLUGIN_NAME"
LEGACY_PLUGIN_CACHE_DIR2="$CLAUDE_DIR/plugins/cache/$LEGACY_PLUGIN_MARKETPLACE2/$PLUGIN_NAME"
LEGACY_PLUGIN_CACHE_DIR3="$CLAUDE_DIR/plugins/cache/$LEGACY_PLUGIN_MARKETPLACE3/$PLUGIN_NAME"
PLUGIN_BUNDLE_MARKER_FILE=".omg-plugin-bundle"

ACTION="install"
ACTION_EXPLICIT=false
DRY_RUN=false
NON_INTERACTIVE=false
MERGE_POLICY="ask"
FRESH_INSTALL=false
INSTALL_AS_PLUGIN=false
USE_SYMLINK=false
ERRORS=0
OMG_MANIFEST="$CLAUDE_DIR/.omg-manifest"
NEW_MANIFEST_ENTRIES=()

V3_RULES=(
    "00-truth-evidence.md" "01-enforcement-map.md" "02-doc-check.md"
    "03-working-memory.md" "04-quality-gate.md" "05-structured-reports.md"
    "06-infra-safety.md" "07-cross-model.md" "08-big-picture.md"
    "09-surgical-changes.md" "10-code-simplifier.md" "11-dependency-safety.md"
    "12-circuit-breaker.md" "13-planning-checklist.md" "14-auto-commands.md"
    "15-context-management.md" "16-honest-testing.md" "17-ensemble-collaboration.md"
    "18-collaborative-solving.md" "19-outside-in.md" "20-project-identity.md"
    "21-verified-claims.md" "22-auto-plugin-mcp.md"
)
V3_AGENTS_REMOVE=(cross-validator.md dependency-guardian.md infra-guardian.md perf-analyst.md ui-reviewer.md)
OLD_OMG_AGENTS=(architect.md critic.md executor.md qa-tester.md escalation-router.md)
V3_COMMANDS_REMOVE=(cross-review.md simplify.md)
V4_COMMANDS_REMOVE=(
    code-review.md deep-plan.md domain-init.md escalate.md handoff.md
    health-check.md learn.md project-init.md security-review.md
)

# Dynamic hook discovery — no hardcoded list.
# Used by remove_omg_files() as fallback when manifest is absent.
build_omg_hooks_list() {
    OMG_HOOKS=()
    for f in "$SCRIPT_DIR"/hooks/*.py; do
        [ -f "$f" ] && OMG_HOOKS+=("$(basename "$f")")
    done
}

usage() {
    cat <<EOF
OMG Setup Manager

Usage:
  ./OMG-setup.sh <action> [OPTIONS]
  ./OMG-setup.sh [OPTIONS]             # defaults to install
  ./OMG-setup.sh                       # interactive menu in terminal mode

Actions:
  install      Install or upgrade OMG components
  update       Alias of install (explicit update mode)
  reinstall    Clean reinstall (remove OMG files, then install)
  uninstall    Remove OMG-managed files from ~/.claude

Options:
  --fresh            For install/update: clean reinstall before install
  --symlink          Use symlinks instead of copies (dev mode - live updates)
  --install-as-plugin
                     Install plugin bundle (plugin.json + MCP + HUD) together
  --dry-run          Show what would happen without writing files
  --non-interactive  Skip prompts (CI/automation mode)
  --merge-policy=X   Settings merge: ask (default), apply, skip
  -h, --help         Show this help

Examples:
  ./OMG-setup.sh install
  ./OMG-setup.sh install --symlink              # Dev mode: live updates from repo
  ./OMG-setup.sh install --install-as-plugin
  ./OMG-setup.sh update --non-interactive --merge-policy=apply
  ./OMG-setup.sh reinstall --dry-run
  ./OMG-setup.sh uninstall --dry-run
EOF
}

is_standalone_installed() {
    [ -f "$CLAUDE_DIR/hooks/.omg-version" ] || [ -d "$CLAUDE_DIR/omg-runtime" ]
}

is_plugin_installed() {
    local marker_new="$PLUGIN_CACHE_DIR/$PLUGIN_BUNDLE_MARKER_FILE"
    local marker_legacy="$LEGACY_PLUGIN_CACHE_DIR/$PLUGIN_BUNDLE_MARKER_FILE"
    if [ -f "$marker_new" ] || [ -f "$marker_legacy" ]; then
        return 0
    fi
    local installed_plugins="$CLAUDE_DIR/plugins/installed_plugins.json"
    if [ -f "$installed_plugins" ] && grep -Eq "\"$PLUGIN_REF\"|\"$LEGACY_PLUGIN_REF\"" "$installed_plugins" 2>/dev/null; then
        return 0
    fi
    return 1
}

prompt_start_action() {
    if $ACTION_EXPLICIT || $NON_INTERACTIVE || $DRY_RUN; then
        return 0
    fi

    local standalone_installed=false
    local plugin_installed=false
    is_standalone_installed && standalone_installed=true
    is_plugin_installed && plugin_installed=true

    echo ""
    echo "Select OMG setup action:"
    echo "  1. Install standalone"
    if $standalone_installed; then
        echo "  2. Update standalone"
    fi
    echo "  3. Install as plugin"
    if $plugin_installed; then
        echo "  4. Update plugin install"
    fi
    echo "  5. Uninstall"
    echo "  0. Cancel"
    echo ""

    read -p "Choose [1/2/3/4/5/0]: " -r
    case "${REPLY:-}" in
        1)
            ACTION="install"
            INSTALL_AS_PLUGIN=false
            ;;
        2)
            if $standalone_installed; then
                ACTION="update"
                INSTALL_AS_PLUGIN=false
            else
                echo "Standalone update unavailable (not installed)."
                exit 1
            fi
            ;;
        3)
            ACTION="install"
            INSTALL_AS_PLUGIN=true
            ;;
        4)
            if $plugin_installed; then
                ACTION="update"
                INSTALL_AS_PLUGIN=true
            else
                echo "Plugin update unavailable (plugin install not detected)."
                exit 1
            fi
            ;;
        5)
            ACTION="uninstall"
            ;;
        0)
            echo "Cancelled by user."
            exit 0
            ;;
        *)
            echo "Invalid selection."
            exit 1
            ;;
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
            help|-h|--help)
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
            --merge-policy=*) MERGE_POLICY="${arg#*=}" ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $arg"
                echo ""
                usage
                exit 1
                ;;
        esac
    done

    if [ "$ACTION" = "reinstall" ]; then
        FRESH_INSTALL=true
    fi

    if [ ! -t 0 ] || [ -n "${npm_lifecycle_event:-}" ] || [ -n "${npm_execpath:-}" ]; then
        NON_INTERACTIVE=true
    fi

    # Auto-enable plugin mode for npm installs
    if [ -n "${npm_execpath:-}" ] || [ -n "${npm_lifecycle_event:-}" ]; then
        INSTALL_AS_PLUGIN=true
    fi
}

preflight() {
    echo "Pre-flight checks..."
    if ! command -v python3 &>/dev/null; then
        echo "  ❌ python3 not found. Install: https://www.python.org/downloads/"
        exit 1
    fi
    local py_ver py_maj py_min
    py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    py_maj=$(echo "$py_ver" | cut -d. -f1)
    py_min=$(echo "$py_ver" | cut -d. -f2)
    if [ "$py_maj" -lt 3 ] || { [ "$py_maj" -eq 3 ] && [ "$py_min" -lt 8 ]; }; then
        echo "  ❌ Python $py_ver found, 3.8+ required"
        exit 1
    fi
    echo "  ✓ Python $py_ver"
}

ensure_backup() {
    if ! $DRY_RUN; then
        mkdir -p "$BACKUP_DIR"
        for dir in rules hooks agents commands; do
            [ -d "$CLAUDE_DIR/$dir" ] && cp -r "$CLAUDE_DIR/$dir" "$BACKUP_DIR/$dir" 2>/dev/null || true
        done
        [ -f "$CLAUDE_DIR/settings.json" ] && cp "$CLAUDE_DIR/settings.json" "$BACKUP_DIR/"
        prune_old_backups
    fi
}

prune_old_backups() {
    local backups=()
    while IFS= read -r path; do
        backups+=("$path")
    done < <(find "$CLAUDE_DIR" -maxdepth 1 -type d -name ".omg-backup-*" | sort)

    local total=${#backups[@]}
    if [ "$total" -le 2 ]; then
        return 0
    fi

    local remove_count=$((total - 2))
    for old in "${backups[@]:0:$remove_count}"; do
        [[ "$old" == "$CLAUDE_DIR"/* ]] || {
            echo "ERROR: backup prune target outside expected directory: $old" >&2
            exit 1
        }
        rm -rf "$old"
    done
}

is_omg_managed_command_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        return 1
    fi

    if grep -q "OMG-AUTO-COMPAT-ALIAS" "$file" 2>/dev/null; then
        return 0
    fi
    if grep -q "OMG-MANAGED-COMMAND" "$file" 2>/dev/null; then
        return 0
    fi

    local base
    base="$(basename "$file")"
    if [[ "$base" == OMG:* ]] && grep -q "/OMG:" "$file" 2>/dev/null; then
        return 0
    fi
    return 1
}

mark_omg_managed_command_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        return 0
    fi
    if ! grep -q "OMG-MANAGED-COMMAND" "$file" 2>/dev/null; then
        printf "\n<!-- OMG-MANAGED-COMMAND -->\n" >> "$file"
    fi
}

# Install a file or directory - either copy or symlink based on USE_SYMLINK
# Usage: install_file <source> <target> [type: file|dir]
install_file() {
    local src="$1"
    local target="$2"
    local type="${3:-file}"
    
    if $USE_SYMLINK; then
        # In symlink mode, create symlink from target -> source
        # First remove existing file/dir if present
        if [ -e "$target" ] || [ -L "$target" ]; then
            rm -rf "$target"
        fi
        ln -s "$src" "$target"
    else
        # In copy mode, do regular copy
        if [ "$type" = "dir" ]; then
            cp -R "$src" "$target"
        else
            cp "$src" "$target"
        fi
    fi
}

track_file() {
    NEW_MANIFEST_ENTRIES+=("$1")
}

reconcile_stale_files() {
    if [ ! -f "$OMG_MANIFEST" ]; then
        echo "  (no previous manifest — first install, skipping reconciliation)"
        return 0
    fi
    local stale=0
    while IFS= read -r old_entry; do
        [ -n "$old_entry" ] || continue
        [[ "$old_entry" == "#"* ]] && continue
        local found=false
        for new_entry in "${NEW_MANIFEST_ENTRIES[@]}"; do
            if [ "$old_entry" = "$new_entry" ]; then
                found=true
                break
            fi
        done
        if ! $found; then
            local target="$CLAUDE_DIR/$old_entry"
            if [ -f "$target" ]; then
                if ! $DRY_RUN; then
                    rm -f "$target"
                fi
                echo "  - $old_entry (removed from source)"
                stale=$((stale + 1))
            fi
        fi
    done < "$OMG_MANIFEST"
    if [ $stale -eq 0 ]; then
        echo "  (no stale files)"
    elif $DRY_RUN; then
        echo "  (dry-run: would remove $stale stale file(s))"
    else
        echo "  ✓ Cleaned $stale stale file(s)"
    fi
}

write_omg_manifest() {
    if ! $DRY_RUN; then
        printf '%s\n' "${NEW_MANIFEST_ENTRIES[@]}" | sort > "$OMG_MANIFEST"
    fi
}

prune_plugin_mcp_from_settings() {
    local mcp_path="$CLAUDE_DIR/.mcp.json"
    if [ ! -f "$mcp_path" ]; then
        return 0
    fi
    python3 - "$mcp_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

servers = data.get("mcpServers")
if not isinstance(servers, dict):
    print("0")
    raise SystemExit(0)

removed = 0
for key in ("context7", "filesystem", "websearch", "chrome-devtools"):
    if key in servers:
        servers.pop(key, None)
        removed += 1

if removed:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

print(str(removed))
PY
}

merge_plugin_mcp_into_settings() {
    local mcp_path="$CLAUDE_DIR/.mcp.json"
    local source_mcp_path="$SCRIPT_DIR/.mcp.json"
    python3 - "$mcp_path" "$source_mcp_path" <<'PY'
import json
import sys
from pathlib import Path

mcp_path = Path(sys.argv[1])
source_mcp_path = Path(sys.argv[2])

mcp_config = {}
if mcp_path.exists():
    try:
        mcp_config = json.loads(mcp_path.read_text(encoding="utf-8"))
    except Exception:
        mcp_config = {}
if not isinstance(mcp_config, dict):
    mcp_config = {}

try:
    source_mcp = json.loads(source_mcp_path.read_text(encoding="utf-8"))
except Exception:
    source_mcp = {}

incoming = source_mcp.get("mcpServers") if isinstance(source_mcp, dict) else {}
if not isinstance(incoming, dict):
    incoming = {}

servers = mcp_config.get("mcpServers")
if not isinstance(servers, dict):
    servers = {}
for key, value in incoming.items():
    if key not in servers:
        servers[key] = value
mcp_config["mcpServers"] = servers

mcp_path.parent.mkdir(parents=True, exist_ok=True)
mcp_path.write_text(json.dumps(mcp_config, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print(str(len(incoming)))
PY
}

write_plugin_mcp_file() {
    local target_path="$1"
    local source_mcp_path="$SCRIPT_DIR/.mcp.json"
    python3 - "$target_path" "$source_mcp_path" <<'PY'
import json
import sys
from pathlib import Path

target_path = Path(sys.argv[1])
source_mcp_path = Path(sys.argv[2])

try:
    source_mcp = json.loads(source_mcp_path.read_text(encoding="utf-8"))
except Exception:
    source_mcp = {}

mcp_servers = source_mcp.get("mcpServers") if isinstance(source_mcp, dict) else {}
if not isinstance(mcp_servers, dict):
    mcp_servers = {}

payload = {"mcpServers": mcp_servers}
target_path.parent.mkdir(parents=True, exist_ok=True)
target_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print(str(len(mcp_servers)))
PY
}

register_plugin_in_registry() {
    local plugin_ref="$1"
    local install_path="$2"
    local version="$3"
    local settings_path="$CLAUDE_DIR/settings.json"
    local installed_plugins_path="$CLAUDE_DIR/plugins/installed_plugins.json"

    python3 - "$settings_path" "$installed_plugins_path" "$plugin_ref" "$install_path" "$version" <<'PY'
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

settings_path = Path(sys.argv[1])
installed_plugins_path = Path(sys.argv[2])
plugin_ref = sys.argv[3]
install_path = sys.argv[4]
version = sys.argv[5]
now = datetime.now(timezone.utc).isoformat()

settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        settings = {}
if not isinstance(settings, dict):
    settings = {}
enabled = settings.get("enabledPlugins")
if not isinstance(enabled, dict):
    enabled = {}
enabled[plugin_ref] = True
settings["enabledPlugins"] = enabled
settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

installed = {}
if installed_plugins_path.exists():
    try:
        installed = json.loads(installed_plugins_path.read_text(encoding="utf-8"))
    except Exception:
        installed = {}
if not isinstance(installed, dict):
    installed = {}
installed["version"] = 2
plugins = installed.get("plugins")
if not isinstance(plugins, dict):
    plugins = {}
plugins[plugin_ref] = [{
    "scope": "user",
    "installPath": install_path,
    "version": version,
    "installedAt": now,
    "lastUpdated": now,
}]
installed["plugins"] = plugins
installed_plugins_path.parent.mkdir(parents=True, exist_ok=True)
installed_plugins_path.write_text(json.dumps(installed, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

unregister_plugin_from_registry() {
    local plugin_ref="$1"
    local settings_path="$CLAUDE_DIR/settings.json"
    local installed_plugins_path="$CLAUDE_DIR/plugins/installed_plugins.json"

    python3 - "$settings_path" "$installed_plugins_path" "$plugin_ref" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
installed_plugins_path = Path(sys.argv[2])
plugin_ref = sys.argv[3]

if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        settings = {}
    if isinstance(settings, dict):
        enabled = settings.get("enabledPlugins")
        if isinstance(enabled, dict) and plugin_ref in enabled:
            enabled.pop(plugin_ref, None)
            settings["enabledPlugins"] = enabled
            settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

if installed_plugins_path.exists():
    try:
        installed = json.loads(installed_plugins_path.read_text(encoding="utf-8"))
    except Exception:
        installed = {}
    if isinstance(installed, dict):
        plugins = installed.get("plugins")
        if isinstance(plugins, dict) and plugin_ref in plugins:
            plugins.pop(plugin_ref, None)
            installed["plugins"] = plugins
            installed_plugins_path.write_text(json.dumps(installed, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

remove_omg_files() {
    if ! $DRY_RUN; then
        local plugin_bundle_marker="$PLUGIN_CACHE_DIR/$PLUGIN_BUNDLE_MARKER_FILE"
        local plugin_bundle_marker_legacy="$LEGACY_PLUGIN_CACHE_DIR/$PLUGIN_BUNDLE_MARKER_FILE"
        local remove_plugin_managed_mcp=false
        if [ -f "$plugin_bundle_marker" ] || [ -f "$plugin_bundle_marker_legacy" ]; then
            remove_plugin_managed_mcp=true
        fi

        # Use manifest for precise removal if available.
        if [ -f "$OMG_MANIFEST" ]; then
            while IFS= read -r entry; do
                [ -n "$entry" ] || continue
                [[ "$entry" == "#"* ]] && continue
                rm -f "$CLAUDE_DIR/$entry"
            done < "$OMG_MANIFEST"
            rm -f "$OMG_MANIFEST"
        fi

        # Also remove by pattern (covers pre-manifest installs + compat aliases).
        build_omg_hooks_list
        for h in "${OMG_HOOKS[@]}"; do
            rm -f "$CLAUDE_DIR/hooks/$h"
        done
        rm -f "$CLAUDE_DIR/hooks/.omg-version" "$CLAUDE_DIR/hooks/.omg-coexist"

        # Remove OMG rules and old v3 rule set.
        for r in "$CLAUDE_DIR"/rules/0[0-4]-*.md; do
            [ -f "$r" ] && rm "$r"
        done
        for rule in "${V3_RULES[@]}"; do
            rm -f "$CLAUDE_DIR/rules/$rule"
        done

        # Remove OMG agents, commands, templates.
        rm -f "$CLAUDE_DIR"/agents/omg-*.md
        if [ -d "$CLAUDE_DIR/commands" ]; then
            while IFS= read -r cmd_path; do
                if [ -n "$cmd_path" ] && is_omg_managed_command_file "$cmd_path"; then
                    rm -f "$cmd_path"
                fi
            done < <(find "$CLAUDE_DIR/commands" -maxdepth 1 -type f -name "*.md" 2>/dev/null | sort)
        fi
        [[ "$CLAUDE_DIR/templates/omg" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/templates/omg" >&2; exit 1; }
        rm -rf "$CLAUDE_DIR/templates/omg"
        [[ "$CLAUDE_DIR/omg-runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/omg-runtime" >&2; exit 1; }
        rm -rf "$CLAUDE_DIR/omg-runtime"

        [[ "$PLUGIN_CACHE_DIR" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $PLUGIN_CACHE_DIR" >&2; exit 1; }
        rm -rf "$PLUGIN_CACHE_DIR"
        [[ "$LEGACY_PLUGIN_CACHE_DIR" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $LEGACY_PLUGIN_CACHE_DIR" >&2; exit 1; }
        rm -rf "$LEGACY_PLUGIN_CACHE_DIR"
        # Remove legacy oh-advanced-layer cache if present
        if [ -d "$LEGACY_PLUGIN_CACHE_DIR2" ]; then
            ! $DRY_RUN && rm -rf "$LEGACY_PLUGIN_CACHE_DIR2"
        fi
        # Remove legacy trac3er cache if present
        if [ -d "$LEGACY_PLUGIN_CACHE_DIR3" ]; then
            ! $DRY_RUN && rm -rf "$LEGACY_PLUGIN_CACHE_DIR3"
        fi
        rm -f "$CLAUDE_DIR/hud/omg-hud.mjs"
        unregister_plugin_from_registry "$PLUGIN_REF"
        unregister_plugin_from_registry "$LEGACY_PLUGIN_REF"
        unregister_plugin_from_registry "$LEGACY_PLUGIN_REF2"
        unregister_plugin_from_registry "$LEGACY_PLUGIN_REF3"

        if $remove_plugin_managed_mcp; then
            local pruned_mcp=0
            pruned_mcp=$(prune_plugin_mcp_from_settings)
            if [ "${pruned_mcp:-0}" -gt 0 ]; then
                echo "  ✓ Plugin-managed MCP servers removed from .mcp.json ($pruned_mcp)"
            fi
        fi
    fi
}

sync_marketplace_cache() {
    local marketplace_name="$1"
    local git_url="$2"
    local marketplace_dir="$CLAUDE_DIR/plugins/marketplaces/$marketplace_name"

    if [ -d "$marketplace_dir" ] && [ -n "$(ls -A "$marketplace_dir" 2>/dev/null)" ]; then
        echo "  ~ Marketplace cache already populated, skipping sync"
        return 0
    fi

    echo "  Syncing marketplace cache for '$marketplace_name'..."

    if command -v claude >/dev/null 2>&1; then
        if claude plugin marketplace update "$marketplace_name" >/dev/null 2>&1; then
            echo "  ✓ Marketplace cache synced via claude CLI"
            return 0
        fi
    fi

    if command -v git >/dev/null 2>&1; then
        mkdir -p "$marketplace_dir"
        if git clone --depth=1 "$git_url" "$marketplace_dir" >/dev/null 2>&1; then
            echo "  ✓ Marketplace cache cloned via git"
            return 0
        fi
        rmdir "$marketplace_dir" 2>/dev/null || true
    fi

    echo "  ~ Marketplace sync skipped (claude CLI and git unavailable or no network)"
}

register_marketplace_in_known_marketplaces() {
    local marketplace_name="$1"
    local git_url="$2"
    local km_path="$CLAUDE_DIR/plugins/known_marketplaces.json"

    python3 - "$km_path" "$marketplace_name" "$git_url" <<'PY'
import json, sys
from pathlib import Path
from datetime import datetime, timezone

km_path = Path(sys.argv[1])
marketplace_name = sys.argv[2]
git_url = sys.argv[3]
install_location = str(Path.home() / ".claude" / "plugins" / "marketplaces" / marketplace_name)
now = datetime.now(timezone.utc).isoformat()

km = {}
if km_path.exists():
    try:
        km = json.loads(km_path.read_text(encoding="utf-8"))
    except Exception:
        km = {}
if not isinstance(km, dict):
    km = {}

# Remove any stale entries that point to the same install path
stale_keys = [
    k for k, v in km.items()
    if isinstance(v, dict) and isinstance(v.get("source"), dict)
    and isinstance(v["source"].get("path"), str)
    and "OMG" in v["source"]["path"]
    and k != marketplace_name
]
for k in stale_keys:
    km.pop(k)

km[marketplace_name] = {
    "source": {
        "source": "git",
        "url": git_url
    },
    "installLocation": install_location,
    "lastUpdated": now,
}

km_path.parent.mkdir(parents=True, exist_ok=True)
km_path.write_text(json.dumps(km, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print(f"  ✓ Marketplace '{marketplace_name}' registered as git source in known_marketplaces.json")
PY
}

install_plugin_bundle() {
    local plugin_ref="$PLUGIN_REF"
    local plugin_root="$PLUGIN_CACHE_DIR/$VERSION"
    local plugin_manifest_src="$SCRIPT_DIR/.claude-plugin/plugin.json"
    local plugin_manifest_target="$plugin_root/.claude-plugin/plugin.json"
    local plugin_mcp_target="$plugin_root/.mcp.json"
    local hud_src="$SCRIPT_DIR/hud/omg-hud.mjs"
    local hud_target="$CLAUDE_DIR/hud/omg-hud.mjs"

    echo "  Plugin bundle mode enabled: install plugin + MCP + HUD together"
    if $DRY_RUN; then
        echo "  (would install plugin bundle under $plugin_root and deploy HUD to $hud_target)"
        echo "  (would register plugin in ~/.claude/plugins/installed_plugins.json and enable it in settings.json)"
        echo "  (would merge plugin MCP servers into .mcp.json)"
        return 0
    fi

    mkdir -p "$plugin_root/.claude-plugin"
    mkdir -p "$CLAUDE_DIR/hud"
    cp "$plugin_manifest_src" "$plugin_manifest_target"
    
    # Provide a fallback .mcp.json if not shipped in npm package
    if [ ! -f "$SCRIPT_DIR/.mcp.json" ]; then
        local _fallback_mcp_dir
        _fallback_mcp_dir=$(mktemp -d)
        cat > "$_fallback_mcp_dir/.mcp.json" <<'FALLBACK_MCP'
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    "websearch": {
      "command": "npx",
      "args": ["-y", "@zhafron/mcp-web-search"]
    },
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
FALLBACK_MCP
        SCRIPT_DIR="$_fallback_mcp_dir" write_plugin_mcp_file "$plugin_mcp_target" >/dev/null
        rm -rf "$_fallback_mcp_dir"
    else
        write_plugin_mcp_file "$plugin_mcp_target" >/dev/null
    fi
    
    cp "$hud_src" "$hud_target"

    # Register HUD as statusLine in user settings.json
    python3 - "$CLAUDE_DIR/settings.json" "$hud_target" <<'HUD_PY'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
hud_path = sys.argv[2]

settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        settings = {}
if not isinstance(settings, dict):
    settings = {}

existing = settings.get("statusLine")
# Only set if not already set, or if it's a previous OMG/OAL HUD
should_update = (
    not isinstance(existing, dict) or
    any(kw in str(existing.get("command", "")) for kw in ["omg-hud", "oal-hud", "omc-hud"])
)

if should_update:
    settings["statusLine"] = {
        "type": "command",
        "command": f"node {hud_path}"
    }
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print("  ✓ statusLine registered for OMG HUD")
else:
    print("  ~ statusLine already set to custom config (not overwriting)")
HUD_PY

    # Write version companion file for HUD self-identification
    local pkg_version
    pkg_version=$(
        python3 - "$SCRIPT_DIR/package.json" 2>/dev/null <<'PY' || echo "1.0.5"
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh)["version"])
PY
    )
    printf '%s\n' "$pkg_version" > "$CLAUDE_DIR/hud/.omg-version"

    mkdir -p "$PLUGIN_CACHE_DIR"
    printf '%s\n' "omg-plugin-bundle-v1" > "$PLUGIN_CACHE_DIR/$PLUGIN_BUNDLE_MARKER_FILE"

    unregister_plugin_from_registry "$LEGACY_PLUGIN_REF"
    unregister_plugin_from_registry "$LEGACY_PLUGIN_REF2"
    unregister_plugin_from_registry "$LEGACY_PLUGIN_REF3"
    register_plugin_in_registry "$plugin_ref" "$plugin_root" "$VERSION"
    merge_plugin_mcp_into_settings >/dev/null

    track_file "plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME/$VERSION/.claude-plugin/plugin.json"
    track_file "plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME/$VERSION/.mcp.json"
    track_file "plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME/$PLUGIN_BUNDLE_MARKER_FILE"
    track_file "hud/omg-hud.mjs"
    register_marketplace_in_known_marketplaces "$PLUGIN_MARKETPLACE" "https://github.com/trac3er00/OMG.git"
    sync_marketplace_cache "$PLUGIN_MARKETPLACE" "https://github.com/trac3er00/OMG.git"
    echo "  ✓ Plugin bundle installed and registered in Claude plugin settings"
}

run_uninstall() {
    echo "═══════════════════════════════════════════════════════════════"
    echo "  OMG Setup Manager — uninstall"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    if $DRY_RUN; then
        echo "  *** DRY RUN — no files will be changed ***"
        echo ""
    fi

    preflight

    local existing_ver=""
    if [ -f "$CLAUDE_DIR/hooks/.omg-version" ]; then
        existing_ver=$(cat "$CLAUDE_DIR/hooks/.omg-version" 2>/dev/null || echo "")
    fi
    if [ -n "$existing_ver" ]; then
        echo "  ✓ Existing OMG install: $existing_ver"
    else
        echo "  ~ No .omg-version marker found; uninstall will still remove known OMG files."
    fi

    if ! $NON_INTERACTIVE && ! $DRY_RUN; then
        read -p "Proceed with uninstall? [y/N] " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Cancelled."
            exit 0
        fi
    fi

    echo ""
    echo "Uninstall: removing OMG-managed files from $CLAUDE_DIR"
    ensure_backup
    if ! $DRY_RUN; then
        echo "  ✓ Backup: $BACKUP_DIR"
    else
        echo "  (would backup to $BACKUP_DIR)"
    fi
    remove_omg_files
    if $DRY_RUN; then
        echo "  (would remove OMG hooks/rules/agents/commands/templates)"
    else
        echo "  ✓ Removed OMG hooks/rules/agents/commands/templates"
    fi

    echo ""
    echo "Uninstall complete."
    echo "  ✓ If plugin bundle was installed, plugin + MCP + HUD were removed together"
    echo "Preserved:"
    echo "  - $CLAUDE_DIR/settings.json"
    echo "  - project .omg/ data"
    echo "  - non-OMG custom files"
}

run_install_like() {
    local existing_ver=""
    local removed=0
    local installed_rules=0
    local installed_hooks=0
    local hook_errors=0
    local installed_agents=0
    local installed_cmds=0

    echo "═══════════════════════════════════════════════════════════════"
    echo "  OMG Setup Manager — $ACTION"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    if $DRY_RUN; then
        echo "  *** DRY RUN — no files will be changed ***"
        echo ""
    fi

    preflight

    if [ -f "$CLAUDE_DIR/hooks/.omg-version" ]; then
        existing_ver=$(cat "$CLAUDE_DIR/hooks/.omg-version" 2>/dev/null || echo "")
    fi

    if [ "$ACTION" = "update" ] && [ -z "$existing_ver" ]; then
        echo "  ~ No existing OMG install detected. update will proceed as install."
    fi

    if [ -n "$existing_ver" ]; then
        echo "  ✓ Existing: $existing_ver → target $VERSION"
    else
        echo "  ✓ Fresh install"
    fi
    echo "  ✓ Standalone mode: OMG-only command surface (standalone mode)"

    if $FRESH_INSTALL; then
        echo ""
        echo "Fresh/reinstall mode: remove OMG files before install."
        if ! $NON_INTERACTIVE && ! $DRY_RUN; then
            read -p "Proceed with fresh cleanup? [y/N] " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Cancelled."
                exit 0
            fi
        fi

        ensure_backup
        if ! $DRY_RUN; then
            echo "  ✓ Backup: $BACKUP_DIR"
        else
            echo "  (would backup to $BACKUP_DIR)"
        fi
        remove_omg_files
        if $DRY_RUN; then
            echo "  (would remove OMG hooks/rules/agents/commands/templates)"
        else
            echo "  ✓ Clean slate ready"
        fi
        existing_ver=""
    fi

    if [ -n "$existing_ver" ] && ! $FRESH_INSTALL; then
        echo ""
        echo "Step 0/7: Backup existing installation..."
        ensure_backup
        if ! $DRY_RUN; then
            echo "  ✓ Backup: $BACKUP_DIR"
        else
            echo "  (would backup to $BACKUP_DIR)"
        fi
    fi

    echo ""
    echo "Step 1/7: Remove deprecated files..."

    for rule in "${V3_RULES[@]}"; do
        target="$CLAUDE_DIR/rules/$rule"
        if [ -f "$target" ]; then
            ! $DRY_RUN && rm "$target"
            echo "  - rules/$rule"
            removed=$((removed + 1))
        fi
    done

    for agent in "${V3_AGENTS_REMOVE[@]}"; do
        target="$CLAUDE_DIR/agents/$agent"
        if [ -f "$target" ]; then
            ! $DRY_RUN && rm "$target"
            echo "  - agents/$agent (v3 deprecated)"
            removed=$((removed + 1))
        fi
    done

    for agent in "${OLD_OMG_AGENTS[@]}"; do
        target="$CLAUDE_DIR/agents/$agent"
        if [ -f "$target" ]; then
            if grep -q "OMG\|omg\|circuit.breaker\|escalat" "$target" 2>/dev/null; then
                ! $DRY_RUN && rm "$target"
                echo "  - agents/$agent (renamed to omg-$agent)"
                removed=$((removed + 1))
            else
                echo "  ~ agents/$agent (kept — appears to be non-OMG/custom)"
            fi
        fi
    done

    for cmd in "${V3_COMMANDS_REMOVE[@]}" "${V4_COMMANDS_REMOVE[@]}"; do
        target="$CLAUDE_DIR/commands/$cmd"
        if [ -f "$target" ]; then
            if is_omg_managed_command_file "$target"; then
                ! $DRY_RUN && rm "$target"
                echo "  - commands/$cmd (v4 → OMG:$cmd)"
                removed=$((removed + 1))
            else
                echo "  ~ commands/$cmd (kept — appears to be non-OMG/custom)"
            fi
        fi
    done

    if compgen -G "$CLAUDE_DIR/commands/*omc*.md" > /dev/null; then
        for cmd in "$CLAUDE_DIR"/commands/*omc*.md; do
            [ -f "$cmd" ] || continue
            if is_omg_managed_command_file "$cmd"; then
                ! $DRY_RUN && rm "$cmd"
                echo "  - commands/$(basename "$cmd") (removed legacy command)"
                removed=$((removed + 1))
            fi
        done
    fi

    if [ -d "$CLAUDE_DIR/hooks/__pycache__" ]; then
        ! $DRY_RUN && rm -rf "$CLAUDE_DIR/hooks/__pycache__"
        removed=$((removed + 1))
    fi
    ! $DRY_RUN && find "$CLAUDE_DIR/hooks/" -name "*.pyc" -delete 2>/dev/null || true
    [ $removed -eq 0 ] && echo "  (nothing to remove)" || echo "  ✓ Removed $removed deprecated files"

    echo ""
    echo "Step 2/7: Core Rules → $CLAUDE_DIR/rules/"
    ! $DRY_RUN && mkdir -p "$CLAUDE_DIR/rules"
    for f in "$SCRIPT_DIR"/rules/core/*.md; do
        name=$(basename "$f")
        target="$CLAUDE_DIR/rules/$name"
        ! $DRY_RUN && cp "$f" "$target"
        installed_rules=$((installed_rules + 1))
        track_file "rules/$name"
    done
    echo "  ✓ $installed_rules core rules"

    echo ""
    echo "Step 3/7: Hooks → $CLAUDE_DIR/hooks/"
    ! $DRY_RUN && mkdir -p "$CLAUDE_DIR/hooks"
    for f in "$SCRIPT_DIR"/hooks/*.py; do
        name=$(basename "$f")
        target="$CLAUDE_DIR/hooks/$name"
        if ! $DRY_RUN; then
            install_file "$f" "$target"
            if ! $USE_SYMLINK; then
                chmod +x "$target"
            fi
        fi
        if python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
            echo "  ✓ $name"
        else
            echo "  ❌ $name (SYNTAX ERROR)"
            hook_errors=$((hook_errors + 1))
            ERRORS=$((ERRORS + 1))
        fi
        installed_hooks=$((installed_hooks + 1))
        track_file "hooks/$name"
    done
    ! $DRY_RUN && echo "$VERSION" > "$CLAUDE_DIR/hooks/.omg-version"
    echo "  ✓ $installed_hooks hooks ($hook_errors errors)"

    echo ""
    echo "Step 4/7: Agents → $CLAUDE_DIR/agents/"
    ! $DRY_RUN && mkdir -p "$CLAUDE_DIR/agents"
    for f in "$SCRIPT_DIR"/agents/*.md; do
        name=$(basename "$f")
        target="$CLAUDE_DIR/agents/$name"
        if ! $DRY_RUN; then
            [ -f "$target" ] && [ -z "$existing_ver" ] && cp "$target" "$target.bak.$BACKUP_TS"
            install_file "$f" "$target"
        fi
        echo "  ✓ $name"
        installed_agents=$((installed_agents + 1))
        track_file "agents/$name"
    done
    echo "  ✓ $installed_agents agents"

    echo ""
    echo "Step 5/7: Commands → $CLAUDE_DIR/commands/"
    ! $DRY_RUN && mkdir -p "$CLAUDE_DIR/commands"
    for f in "$SCRIPT_DIR"/commands/*.md; do
        name=$(basename "$f")
        if [[ "$name" == *omc* ]]; then
            echo "  - /$(basename "$name" .md) (skipped: legacy alias commands are unsupported)"
            continue
        fi
        target="$CLAUDE_DIR/commands/$name"
        if [ -f "$target" ] && ! is_omg_managed_command_file "$target"; then
            echo "  ~ /$(basename "$name" .md) (kept existing custom command)"
            continue
        fi
        if ! $DRY_RUN; then
            install_file "$f" "$target"
            if ! $USE_SYMLINK; then
                mark_omg_managed_command_file "$target"
            fi
        fi
        echo "  ✓ /$(basename "$name" .md)"
        installed_cmds=$((installed_cmds + 1))
        track_file "commands/$name"
    done
    echo ""
    echo "Step 6/7: Settings + Templates..."
    MERGE="$SCRIPT_DIR/scripts/settings-merge.py"
    TARGET="$CLAUDE_DIR/settings.json"
    SOURCE="$SCRIPT_DIR/settings.json"
    if ! $DRY_RUN; then
        if [ ! -f "$TARGET" ]; then
            cp "$SOURCE" "$TARGET"
            echo "  ✓ Created settings.json"
        else
            if [ "$MERGE_POLICY" = "skip" ]; then
                echo "  ⊘ Skipped settings merge (--merge-policy=skip)"
            elif [ "$MERGE_POLICY" = "apply" ] || $NON_INTERACTIVE; then
                python3 "$MERGE" "$TARGET" "$SOURCE"
                echo "  ✓ Settings merged (auto)"
            else
                echo "  Merging settings.json..."
                dry_run_preview="$(python3 "$MERGE" "$TARGET" "$SOURCE" --dry-run 2>&1)"
                printf '%s\n' "$dry_run_preview" | sed -n '1,5p' | sed 's/^/      /'
                echo ""
                if read -p "  Apply merge? [Y/n] " -n 1 -r 2>/dev/null; then
                    echo ""
                    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                        python3 "$MERGE" "$TARGET" "$SOURCE"
                        echo "  ✓ Settings merged"
                    else
                        echo "  ⊘ Skipped (manual merge needed)"
                    fi
                else
                    # read failed — only auto-apply if we can confirm non-interactive context
                    # non-interactive fallback: check for clear non-interactive indicators
                    if [ ! -t 0 ] || [ -n "${npm_lifecycle_event:-}" ] || [ -n "${npm_execpath:-}" ]; then
                        python3 "$MERGE" "$TARGET" "$SOURCE"
                        echo "  ✓ Settings merged (auto — non-interactive fallback)"
                    else
                        echo "  ⚠ Could not read input. Skipping merge to be safe."
                        echo "    Run manually: ./OMG-setup.sh update --merge-policy=apply"
                    fi
                fi
            fi
        fi

        if $USE_SYMLINK; then
            # In symlink mode, link entire directories for templates
            if [ -e "$CLAUDE_DIR/templates/omg" ] || [ -L "$CLAUDE_DIR/templates/omg" ]; then
                rm -rf "$CLAUDE_DIR/templates/omg"
            fi
            ln -s "$SCRIPT_DIR/templates" "$CLAUDE_DIR/templates/omg"
            # Also link contextual rules
            mkdir -p "$CLAUDE_DIR/templates/omg/contextual-rules"
            for cr in "$SCRIPT_DIR"/rules/contextual/*.md; do
                [ -f "$cr" ] && track_file "templates/omg/contextual-rules/$(basename "$cr")"
            done
        else
            mkdir -p "$CLAUDE_DIR/templates/omg"
            cp "$SCRIPT_DIR"/templates/* "$CLAUDE_DIR/templates/omg/" 2>/dev/null || true
            for t in "$SCRIPT_DIR"/templates/*; do
                [ -f "$t" ] && track_file "templates/omg/$(basename "$t")"
            done
            mkdir -p "$CLAUDE_DIR/templates/omg/contextual-rules"
            cp "$SCRIPT_DIR"/rules/contextual/*.md "$CLAUDE_DIR/templates/omg/contextual-rules/" 2>/dev/null || true
            for cr in "$SCRIPT_DIR"/rules/contextual/*.md; do
                [ -f "$cr" ] && track_file "templates/omg/contextual-rules/$(basename "$cr")"
            done
        fi
        mkdir -p "$CLAUDE_DIR/templates/omg/state/memory"
        mkdir -p "$CLAUDE_DIR/templates/omg/state/learnings"
        mkdir -p "$CLAUDE_DIR/templates/omg/state/ledger"
        echo "  \u2713 State directory templates (memory, learnings, ledger)"
        echo "  \u2713 Templates + contextual rules"

        if $USE_SYMLINK; then
            # In symlink mode, link runtime directories instead of copying
            mkdir -p "$CLAUDE_DIR/omg-runtime/scripts"
            install_file "$SCRIPT_DIR/scripts/omg.py" "$CLAUDE_DIR/omg-runtime/scripts/omg.py"
            
            [[ "$CLAUDE_DIR/omg-runtime/runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/runtime" >&2; exit 1; }
            [[ "$CLAUDE_DIR/omg-runtime/hooks" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/hooks" >&2; exit 1; }
            [[ "$CLAUDE_DIR/omg-runtime/lab" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/lab" >&2; exit 1; }
            
            rm -rf "$CLAUDE_DIR/omg-runtime/runtime" "$CLAUDE_DIR/omg-runtime/hooks" "$CLAUDE_DIR/omg-runtime/lab"
            ln -s "$SCRIPT_DIR/runtime" "$CLAUDE_DIR/omg-runtime/runtime"
            ln -s "$SCRIPT_DIR/hooks" "$CLAUDE_DIR/omg-runtime/hooks"
            ln -s "$SCRIPT_DIR/lab" "$CLAUDE_DIR/omg-runtime/lab"
            
            [[ "$CLAUDE_DIR/omg-runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/omg-runtime" >&2; exit 1; }
            find "$CLAUDE_DIR/omg-runtime" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
            find "$CLAUDE_DIR/omg-runtime" -name "*.pyc" -delete 2>/dev/null || true
            echo "  ✓ Portable runtime → $CLAUDE_DIR/omg-runtime (symlinked to $SCRIPT_DIR)"
        else
            mkdir -p "$CLAUDE_DIR/omg-runtime/scripts"
            cp "$SCRIPT_DIR/scripts/omg.py" "$CLAUDE_DIR/omg-runtime/scripts/omg.py"
            [[ "$CLAUDE_DIR/omg-runtime/runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/omg-runtime/runtime" >&2; exit 1; }
            rm -rf "$CLAUDE_DIR/omg-runtime/runtime" "$CLAUDE_DIR/omg-runtime/hooks" "$CLAUDE_DIR/omg-runtime/lab"
            cp -R "$SCRIPT_DIR/runtime" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/hooks" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/lab" "$CLAUDE_DIR/omg-runtime/"
            [[ "$CLAUDE_DIR/omg-runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/omg-runtime" >&2; exit 1; }
            find "$CLAUDE_DIR/omg-runtime" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
            find "$CLAUDE_DIR/omg-runtime" -name "*.pyc" -delete 2>/dev/null || true
            echo "  ✓ Portable runtime → $CLAUDE_DIR/omg-runtime"
        fi
        if $INSTALL_AS_PLUGIN; then
            install_plugin_bundle
        fi
    else
        echo "  (would merge settings.json + copy templates + provision portable runtime)"
        if $INSTALL_AS_PLUGIN; then
            install_plugin_bundle
        fi
    fi


    echo ""
    echo "Step 7/7: Reconcile stale files..."
    reconcile_stale_files
    write_omg_manifest

    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    if [ $ERRORS -eq 0 ]; then
        echo "  ✅ OMG v1 ${ACTION} completed successfully"
    else
        echo "  ⚠  OMG v1 ${ACTION} completed with $ERRORS error(s)"
    fi
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  Files: $installed_rules rules, $installed_hooks hooks, $installed_agents agents, $installed_cmds commands"
    echo "  Version: $VERSION"
    if $USE_SYMLINK; then
        echo "  Mode: Symlink (live updates from $SCRIPT_DIR)"
        echo "  Source: $SCRIPT_DIR"
    elif $FRESH_INSTALL; then
        echo "  Mode: Fresh reinstall"
    elif [ -n "$existing_ver" ]; then
        echo "  Upgraded: $existing_ver → $VERSION"
        echo "  Backup: $BACKUP_DIR"
    fi
    echo ""
    if $DRY_RUN; then
        echo "  *** DRY RUN — no files were changed ***"
        echo "  Run without --dry-run to apply changes."
    fi
}

main() {
    parse_args "$@"
    prompt_start_action
    case "$ACTION" in
        uninstall) run_uninstall ;;
        install|update|reinstall) run_install_like ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
