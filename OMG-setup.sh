#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BACKUP_TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$CLAUDE_DIR/.omg-backup-$BACKUP_TS"
VERSION="2.2.7"

PLUGIN_NAME="omg"
PLUGIN_MARKETPLACE="omg"
LEGACY_PLUGIN_MARKETPLACE="oh-advanced-layer"
PLUGIN_REF="${PLUGIN_NAME}@${PLUGIN_MARKETPLACE}"
LEGACY_PLUGIN_REF="${PLUGIN_NAME}@${LEGACY_PLUGIN_MARKETPLACE}"
PLUGIN_CACHE_DIR="$CLAUDE_DIR/plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME"
LEGACY_PLUGIN_CACHE_DIR="$CLAUDE_DIR/plugins/cache/$LEGACY_PLUGIN_MARKETPLACE/$PLUGIN_NAME"
PLUGIN_BUNDLE_MARKER_FILE=".omg-plugin-bundle"

ACTION="install"
ACTION_EXPLICIT=false
DRY_RUN=false
NON_INTERACTIVE=false
MERGE_POLICY="ask"
FRESH_INSTALL=false
INSTALL_AS_PLUGIN=false
USE_SYMLINK=false
ENABLE_BROWSER=false
VERIFY_CLEAN=false
REPAIR=false
ADOPTION_MODE="omg-only"
ADOPT_MODE="auto"
OMG_PRESET="safe"
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
  --mode=omg-only|coexist
                     Native OMG adoption mode for overlapping ecosystems
  --adopt=auto       Detect OMG-adjacent ecosystems during install/update
  --preset=safe|balanced|interop|labs|buffet|production
                     User-facing preset for managed OMG features
  --enable-browser   Enable optional OMG browser capability metadata and guidance
  --verify-clean     After uninstall, verify no OMG-managed residue remains
  --repair           With --verify-clean, back up and remove owned residue
  -h, --help         Show this help

Examples:
  ./OMG-setup.sh install
  ./OMG-setup.sh install --symlink              # Dev mode: live updates from repo
  ./OMG-setup.sh install --install-as-plugin
  ./OMG-setup.sh install --mode=coexist --preset=interop
  ./OMG-setup.sh update --non-interactive --merge-policy=apply
  bunx @trac3er/oh-my-god
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
    local anything_installed=false
    is_standalone_installed && standalone_installed=true
    is_plugin_installed && plugin_installed=true
    if $standalone_installed || $plugin_installed; then
        anything_installed=true
    fi

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
    if $anything_installed; then
        echo "  5. Uninstall"
    fi
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
            if $anything_installed; then
                ACTION="uninstall"
            else
                echo "Uninstall unavailable (nothing installed)."
                exit 1
            fi
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
            --enable-browser) ENABLE_BROWSER=true ;;
            --verify-clean) VERIFY_CLEAN=true ;;
            --repair) REPAIR=true ;;
            --merge-policy=*) MERGE_POLICY="${arg#*=}" ;;
            --mode=*) ADOPTION_MODE="${arg#*=}" ;;
            --adopt=*) ADOPT_MODE="${arg#*=}" ;;
            --preset=*) OMG_PRESET="${arg#*=}" ;;
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

    if [ ! -t 0 ]; then
        NON_INTERACTIVE=true
    fi

    # Auto-enable plugin mode for npm/bunx installs
    if [ -n "${npm_execpath:-}" ] || [ -n "${npm_lifecycle_event:-}" ] || [ -n "${BUN_INSTALL:-}" ]; then
        INSTALL_AS_PLUGIN=true
    fi

    case "$ADOPTION_MODE" in
        omg-only|coexist) ;;
        *)
            echo "Unknown adoption mode: $ADOPTION_MODE"
            exit 1
            ;;
    esac

    case "$ADOPT_MODE" in
        auto) ;;
        *)
            echo "Unknown adoption detector mode: $ADOPT_MODE"
            exit 1
            ;;
    esac

    case "$OMG_PRESET" in
        plugins-first)
            OMG_PRESET="interop"
            ;;
        safe|balanced|interop|labs|buffet|production) ;;
        *)
            echo "Unknown OMG preset: $OMG_PRESET"
            exit 1
            ;;
    esac
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
    if [ "$py_maj" -lt 3 ] || { [ "$py_maj" -eq 3 ] && [ "$py_min" -lt 10 ]; }; then
        echo "  ❌ Python $py_ver is not supported. OMG requires Python 3.10 or newer."
        echo "     Python 3.8 and 3.9 are unsupported because OMG depends on"
        echo "     libraries (fastmcp >=2.0) that require Python >= 3.10."
        echo "     Upgrade at: https://www.python.org/downloads/"
        exit 1
    fi
    echo "  ✓ Python $py_ver"
}


verify_install_integrity() {
    local manifest="$SCRIPT_DIR/INSTALL_INTEGRITY.sha256"

    if [ ! -f "$manifest" ]; then
        echo "  ~ No integrity manifest found (skipping hash verification)"
        return 0
    fi

    echo "  Verifying install integrity..."
    local failures=0
    local checked=0

    while IFS= read -r line; do
        # Skip empty lines and comments
        [ -z "$line" ] && continue
        [[ "$line" == "#"* ]] && continue

        local expected_hash file_path
        expected_hash=$(echo "$line" | awk '{print $1}')
        file_path=$(echo "$line" | awk '{print $2}')

        [ -z "$expected_hash" ] || [ -z "$file_path" ] && continue

        local full_path="$SCRIPT_DIR/$file_path"
        if [ ! -f "$full_path" ]; then
            echo "  ❌ INTEGRITY FAILURE: $file_path — file not found"
            echo "     Expected at: $full_path"
            echo "     Action: Re-download or re-clone the OMG source."
            failures=$((failures + 1))
            continue
        fi

        local actual_hash
        if command -v shasum &>/dev/null; then
            actual_hash=$(shasum -a 256 "$full_path" | awk '{print $1}')
        elif command -v sha256sum &>/dev/null; then
            actual_hash=$(sha256sum "$full_path" | awk '{print $1}')
        else
            echo "  ❌ Cannot verify integrity: neither shasum nor sha256sum found"
            echo "     Action: Install coreutils or ensure shasum is available."
            exit 1
        fi

        if [ "$actual_hash" != "$expected_hash" ]; then
            echo "  ❌ INTEGRITY FAILURE: $file_path — hash mismatch"
            echo "     Expected: $expected_hash"
            echo "     Actual:   $actual_hash"
            echo "     Action: Re-download or re-clone the OMG source."
            failures=$((failures + 1))
        fi
        checked=$((checked + 1))
    done < "$manifest"

    if [ $failures -gt 0 ]; then
        echo ""
        echo "  ❌ Install integrity check FAILED ($failures file(s) corrupted or missing)"
        echo "     The installer source does not match the expected integrity manifest."
        echo "     This may indicate a corrupted download, incomplete clone, or tampering."
        echo ""
        echo "     To fix:"
        echo "       1. Re-clone: git clone https://github.com/anthropics/omg.git"
        echo "       2. Or re-download from the official release page"
        echo "       3. Then re-run: ./OMG-setup.sh install"
        exit 1
    fi

    echo "  ✓ Install integrity verified ($checked file(s) checked)"
}

provision_managed_venv() {
    local venv_dir="$CLAUDE_DIR/omg-runtime/.venv"

    if [ ! -f "$venv_dir/bin/python" ]; then
        python3 -m venv "$venv_dir" || {
            echo "  ⚠ Could not create managed venv (continuing without it)"
            return 0
        }
    fi

    if $USE_SYMLINK; then
        "$venv_dir/bin/pip" install --quiet -e "${SCRIPT_DIR}[mcp]" 2>/dev/null || true
    else
        "$venv_dir/bin/pip" install --quiet "${SCRIPT_DIR}[mcp]" 2>/dev/null || true
    fi

    echo "  ✓ Managed venv → $venv_dir"
}

write_managed_mcp_launcher() {
    local launcher_path="$CLAUDE_DIR/omg-runtime/bin/omg-mcp-server.py"
    local runtime_root="$CLAUDE_DIR/omg-runtime"

    mkdir -p "$(dirname "$launcher_path")"
    python3 - "$launcher_path" "$runtime_root" <<'PY'
import json
import sys
from pathlib import Path

launcher_path = Path(sys.argv[1])
runtime_root = Path(sys.argv[2])

content = f"""#!/usr/bin/env python3
from __future__ import annotations

import runpy
import sys
from pathlib import Path

RUNTIME_ROOT = Path({json.dumps(str(runtime_root))})
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

if __name__ == "__main__":
    runpy.run_module("runtime.omg_mcp_server", run_name="__main__")
"""

launcher_path.write_text(content, encoding="utf-8")
launcher_path.chmod(0o755)
PY
}

patch_omg_control_mcp_python() {
    local venv_python="$CLAUDE_DIR/omg-runtime/.venv/bin/python"
    local launcher_path="$CLAUDE_DIR/omg-runtime/bin/omg-mcp-server.py"
    local mcp_paths=(
        "$CLAUDE_DIR/.mcp.json"
        "$PLUGIN_CACHE_DIR/$VERSION/.claude-plugin/mcp.json"
        "$PLUGIN_CACHE_DIR/$VERSION/.mcp.json"
    )

    python3 - "$venv_python" "$launcher_path" "${mcp_paths[@]}" <<'PY'
import json
import sys
from pathlib import Path

venv_python = sys.argv[1]
launcher_path = sys.argv[2]

for raw_path in sys.argv[3:]:
    mcp_path = Path(raw_path)
    if not mcp_path.exists():
        continue
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except Exception:
        continue

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        continue

    omg_control = servers.get("omg-control")
    if isinstance(omg_control, dict):
        omg_control["command"] = venv_python
        omg_control["args"] = [launcher_path]
        mcp_path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

prune_plugin_duplicate_mcp_from_settings() {
    local mcp_path="$CLAUDE_DIR/.mcp.json"
    local plugin_mcp_path="$PLUGIN_CACHE_DIR/$VERSION/.claude-plugin/mcp.json"

    if [ ! -f "$plugin_mcp_path" ]; then
        plugin_mcp_path="$PLUGIN_CACHE_DIR/$VERSION/.mcp.json"
    fi

    if [ ! -f "$mcp_path" ] || [ ! -f "$plugin_mcp_path" ]; then
        return 0
    fi

    python3 - "$mcp_path" "$plugin_mcp_path" <<'PY'
import json
import sys
from pathlib import Path

mcp_path = Path(sys.argv[1])
plugin_mcp_path = Path(sys.argv[2])

try:
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    plugin_data = json.loads(plugin_mcp_path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

servers = data.get("mcpServers")
plugin_servers = plugin_data.get("mcpServers")
if not isinstance(servers, dict) or not isinstance(plugin_servers, dict):
    print("0")
    raise SystemExit(0)

removed = 0
for key, plugin_value in plugin_servers.items():
    if key in servers and servers.get(key) == plugin_value:
        servers.pop(key, None)
        removed += 1

data["mcpServers"] = servers
mcp_path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print(str(removed))
PY
}

prune_legacy_plugin_mcp_from_settings() {
    local mcp_path="$CLAUDE_DIR/.mcp.json"
    local venv_python="$CLAUDE_DIR/omg-runtime/.venv/bin/python"

    if [ ! -f "$mcp_path" ]; then
        return 0
    fi

    python3 - "$mcp_path" "$venv_python" <<'PY'
import json
import sys
from pathlib import Path

mcp_path = Path(sys.argv[1])
venv_python = sys.argv[2]

try:
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

servers = data.get("mcpServers")
if not isinstance(servers, dict):
    print("0")
    raise SystemExit(0)

removed = 0

omg_control = servers.get("omg-control")
if isinstance(omg_control, dict):
    command = omg_control.get("command")
    args = omg_control.get("args")
    if isinstance(args, list) and args == ["-m", "runtime.omg_mcp_server"] and command in {
        "python",
        "python3",
        venv_python,
    }:
        servers.pop("omg-control", None)
        removed += 1

data["mcpServers"] = servers
mcp_path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print(str(removed))
PY
}

configure_hud_status_line() {
    local settings_path="$CLAUDE_DIR/settings.json"
    local hud_path="$CLAUDE_DIR/hud/omg-hud.mjs"

    python3 - "$settings_path" "$hud_path" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
hud_path = Path(sys.argv[2])
desired_command = f'node "{hud_path}"'

settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        settings = {}
if not isinstance(settings, dict):
    settings = {}

status_line = settings.get("statusLine")
if not isinstance(status_line, dict) or not status_line:
    settings["statusLine"] = {
        "type": "command",
        "command": desired_command,
    }
elif "omg-hud.mjs" in str(status_line.get("command") or ""):
    padding = status_line.get("padding")
    settings["statusLine"] = {
        "type": "command",
        "command": desired_command,
    }
    if isinstance(padding, (int, float)):
        settings["statusLine"]["padding"] = padding

settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

remove_hud_status_line() {
    local settings_path="$CLAUDE_DIR/settings.json"

    if [ ! -f "$settings_path" ]; then
        return 0
    fi

    python3 - "$settings_path" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
if not isinstance(settings, dict):
    raise SystemExit(0)

status_line = settings.get("statusLine")
if isinstance(status_line, dict) and "omg-hud.mjs" in str(status_line.get("command") or ""):
    settings.pop("statusLine", None)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

remove_omg_hooks_from_settings() {
    local settings_path="$CLAUDE_DIR/settings.json"
    local hooks_dir="$CLAUDE_DIR/hooks"
    if [ ! -f "$settings_path" ]; then
        return 0
    fi
    if ! command -v python3 &>/dev/null; then
        return 0
    fi
    python3 - "$settings_path" "$hooks_dir" <<'PY'
import json, sys
from pathlib import Path
settings_path = Path(sys.argv[1])
hooks_dir = sys.argv[2]
try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
if not isinstance(settings, dict):
    raise SystemExit(0)
hooks_section = settings.get("hooks")
if not isinstance(hooks_section, dict):
    raise SystemExit(0)
def is_omg_cmd(cmd):
    if not isinstance(cmd, str):
        return False
    return "omg-runtime" in cmd or (hooks_dir + "/") in cmd
def entry_is_omg(entry):
    if not isinstance(entry, dict):
        return False
    nested = entry.get("hooks")
    if isinstance(nested, list) and nested:
        return all(isinstance(h, dict) and is_omg_cmd(h.get("command", "")) for h in nested)
    return is_omg_cmd(entry.get("command", ""))
changed = False
new_hooks = {}
for event, entries in hooks_section.items():
    if not isinstance(entries, list):
        new_hooks[event] = entries
        continue
    filtered = [e for e in entries if not entry_is_omg(e)]
    if len(filtered) < len(entries):
        changed = True
    if filtered:
        new_hooks[event] = filtered
if changed:
    if new_hooks:
        settings["hooks"] = new_hooks
    else:
        settings.pop("hooks", None)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

remove_omg_metadata_from_settings() {
    local settings_path="$CLAUDE_DIR/settings.json"
    if [ ! -f "$settings_path" ]; then
        return 0
    fi
    if ! command -v python3 &>/dev/null; then
        return 0
    fi
    python3 - "$settings_path" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
if not isinstance(settings, dict):
    raise SystemExit(0)

changed = False
if "_omg" in settings:
    settings.pop("_omg", None)
    changed = True

if changed:
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

remove_codex_managed_residue() {
    local codex_dir="${HOME:-$HOME}/.codex"
    [ -d "$codex_dir" ] || return 0

    rm -rf "$codex_dir/.omg"
    rm -f "$codex_dir/bin/omg-codex-hud"
    rm -f "$codex_dir/hud/omg-codex-hud.py"

    if [ -d "$codex_dir/skills" ]; then
        while IFS= read -r skill_dir; do
            [ -f "$skill_dir/.omg-managed-skill" ] || continue
            rm -rf "$skill_dir"
        done < <(find "$codex_dir/skills" -maxdepth 1 -mindepth 1 -type d -name 'omg-*' 2>/dev/null | sort)
    fi
}

emit_uninstall_receipt() {
    local receipt_path="$CLAUDE_DIR/.omg-uninstall-receipt.json"
    local removed_paths_json="${1:-[]}"
    local preserved_paths_json="${2:-[]}"
    local host_configs_json="${3:-[]}"
    if ! command -v python3 &>/dev/null; then
        return 0
    fi
    python3 - "$receipt_path" "$VERSION" "$removed_paths_json" "$preserved_paths_json" "$host_configs_json" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
receipt_path = Path(sys.argv[1])
version = sys.argv[2]
try:
    removed_paths = json.loads(sys.argv[3])
except Exception:
    removed_paths = []
try:
    preserved_paths = json.loads(sys.argv[4])
except Exception:
    preserved_paths = []
try:
    host_configs_cleaned = json.loads(sys.argv[5])
except Exception:
    host_configs_cleaned = []
receipt = {
    "schema": "UninstallReceipt",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "version": version,
    "removed_paths": removed_paths,
    "preserved_paths": preserved_paths,
    "host_configs_cleaned": host_configs_cleaned,
    "status": "ok",
}
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
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

configure_browser_capability() {
    local browser_dir="$CLAUDE_DIR/omg-runtime/browser"
    local browser_state_path="$browser_dir/capability.json"
    local browser_command_json="null"
    local browser_status="missing"

    if command -v playwright >/dev/null 2>&1; then
        browser_command_json='["playwright"]'
        browser_status="ready"
    elif command -v playwright-cli >/dev/null 2>&1; then
        browser_command_json='["playwright-cli"]'
        browser_status="ready"
    elif command -v npx >/dev/null 2>&1; then
        browser_command_json='["npx","playwright"]'
        browser_status="bootstrap-required"
    fi

    if $DRY_RUN; then
        echo "  (would enable browser capability using command: $browser_command_json)"
        return 0
    fi

    mkdir -p "$browser_dir"
    python3 - "$browser_state_path" "$browser_status" "$browser_command_json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
status = sys.argv[2]
command_json = sys.argv[3]
command = json.loads(command_json)
payload = {
    "enabled": True,
    "status": status,
    "command": command,
    "remediation": "Use `npx playwright` or install `@playwright/cli`, then install browsers before running /OMG:browser.",
}
path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
    track_file "omg-runtime/browser/capability.json"
    echo "  ✓ Browser capability enabled"
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
    servers[key] = value
mcp_config["mcpServers"] = servers

mcp_path.parent.mkdir(parents=True, exist_ok=True)
mcp_path.write_text(json.dumps(mcp_config, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print(str(len(incoming)))
PY
}

write_plugin_mcp_file() {
    local target_path="$1"
    local source_mcp_path="$SCRIPT_DIR/.claude-plugin/mcp.json"
    if [ ! -f "$source_mcp_path" ]; then
        source_mcp_path="$SCRIPT_DIR/.mcp.json"
    fi
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

# Plugin installs should only publish OMG-specific MCP servers.
# Generic servers such as filesystem often already exist at project scope.
mcp_servers = {
    key: value
    for key, value in mcp_servers.items()
    if key == "omg-control"
}

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

register_plugin_marketplace() {
    local marketplace_name="$1"
    local install_path="$2"
    local settings_path="$CLAUDE_DIR/settings.json"
    local known_marketplaces_path="$CLAUDE_DIR/plugins/known_marketplaces.json"

    python3 - "$settings_path" "$known_marketplaces_path" "$marketplace_name" "$install_path" <<'PY'
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

settings_path = Path(sys.argv[1])
known_marketplaces_path = Path(sys.argv[2])
marketplace_name = sys.argv[3]
install_path = sys.argv[4]
now = datetime.now(timezone.utc).isoformat()
source = {
    "source": "directory",
    "path": install_path,
}

settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        settings = {}
if not isinstance(settings, dict):
    settings = {}
extra_known = settings.get("extraKnownMarketplaces")
if not isinstance(extra_known, dict):
    extra_known = {}
extra_known[marketplace_name] = {"source": source}
settings["extraKnownMarketplaces"] = extra_known
settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

known_marketplaces = {}
if known_marketplaces_path.exists():
    try:
        known_marketplaces = json.loads(known_marketplaces_path.read_text(encoding="utf-8"))
    except Exception:
        known_marketplaces = {}
if not isinstance(known_marketplaces, dict):
    known_marketplaces = {}
known_marketplaces[marketplace_name] = {
    "source": source,
    "installLocation": install_path,
    "lastUpdated": now,
}
known_marketplaces_path.parent.mkdir(parents=True, exist_ok=True)
known_marketplaces_path.write_text(
    json.dumps(known_marketplaces, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)
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

unregister_plugin_marketplace() {
    local marketplace_name="$1"
    local settings_path="$CLAUDE_DIR/settings.json"
    local known_marketplaces_path="$CLAUDE_DIR/plugins/known_marketplaces.json"

    python3 - "$settings_path" "$known_marketplaces_path" "$marketplace_name" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
known_marketplaces_path = Path(sys.argv[2])
marketplace_name = sys.argv[3]

if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        settings = {}
    if isinstance(settings, dict):
        extra_known = settings.get("extraKnownMarketplaces")
        if isinstance(extra_known, dict) and marketplace_name in extra_known:
            extra_known.pop(marketplace_name, None)
            settings["extraKnownMarketplaces"] = extra_known
            settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

if known_marketplaces_path.exists():
    try:
        known_marketplaces = json.loads(known_marketplaces_path.read_text(encoding="utf-8"))
    except Exception:
        known_marketplaces = {}
    if isinstance(known_marketplaces, dict) and marketplace_name in known_marketplaces:
        known_marketplaces.pop(marketplace_name, None)
        known_marketplaces_path.write_text(
            json.dumps(known_marketplaces, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
PY
}

configure_detected_host_mcp_servers() {
    local managed_python="$CLAUDE_DIR/omg-runtime/.venv/bin/python"
    local managed_launcher="$CLAUDE_DIR/omg-runtime/bin/omg-mcp-server.py"
    if [ ! -x "$managed_python" ]; then
        managed_python="python3"
    fi

    python3 - "$SCRIPT_DIR" "$managed_python" "$managed_launcher" <<'PY'
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
managed_python = sys.argv[2]
managed_launcher = sys.argv[3]

sys.path.insert(0, str(root))

from runtime.install_planner import compute_install_plan, execute_plan  # noqa: E402

detected_clis = {
    host: {"detected": bool(shutil.which(host))}
    for host in ("codex", "gemini", "kimi", "opencode")
}

plan = compute_install_plan(
    project_dir=str(root),
    detected_clis=detected_clis,
    preset="safe",
    mode="focused",
    selected_ids=["omg-control"],
    control_command=managed_python,
    control_args=[managed_launcher],
    selected_servers={
        "omg-control": {
            "command": managed_python,
            "args": [managed_launcher],
        }
    },
    source_root=root,
    include_claude_action=False,
)
plan.pre_checks = []
result = execute_plan(plan)

configured = [action.host for action in plan.actions if action.host in {"codex", "gemini", "kimi", "opencode"}]
if not result.get("errors") and configured:
    print(",".join(configured))
PY
}

remove_detected_host_mcp_servers() {
    python3 - <<'PY'
import json
import os
from pathlib import Path


def remove_codex_section(path: Path, server_name: str) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    headers = {
        f"[mcp_servers.{server_name}]",
        f"[mcp_servers.\"{server_name}\"]",
    }
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() in headers:
            start_idx = idx
            break
    if start_idx is None:
        return False

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break

    updated = lines[:start_idx] + lines[end_idx:]
    content = "".join(updated).lstrip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def remove_json_server(path: Path, server_name: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    mcp_servers = data.get("mcpServers")
    if not isinstance(mcp_servers, dict) or server_name not in mcp_servers:
        return False
    mcp_servers.pop(server_name, None)
    data["mcpServers"] = mcp_servers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True


def remove_opencode_server(path: Path, server_name: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    mcp_servers = data.get("mcp")
    if not isinstance(mcp_servers, dict) or server_name not in mcp_servers:
        return False
    mcp_servers.pop(server_name, None)
    data["mcp"] = mcp_servers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True


removed: list[str] = []
home = Path(os.path.expanduser("~"))
if remove_codex_section(home / ".codex" / "config.toml", "omg-control"):
    removed.append("codex")
if remove_json_server(home / ".gemini" / "settings.json", "omg-control"):
    removed.append("gemini")
if remove_json_server(home / ".kimi" / "mcp.json", "omg-control"):
    removed.append("kimi")
if remove_opencode_server(home / ".config" / "opencode" / "opencode.json", "omg-control"):
    removed.append("opencode")

if removed:
    print(",".join(removed))
PY
}

apply_omg_preset_to_settings() {
    local settings_path="$1"
    local preset="$2"

    if [ ! -f "$settings_path" ]; then
        return 0
    fi

    python3 - "$SCRIPT_DIR" "$settings_path" "$preset" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
settings_path = Path(sys.argv[2])
preset = sys.argv[3]

sys.path.insert(0, str(root))

from runtime.adoption import CANONICAL_VERSION, get_preset_features, resolve_preset

try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except Exception:
    settings = {}

if not isinstance(settings, dict):
    settings = {}

omg = settings.get("_omg")
if not isinstance(omg, dict):
    omg = {}

features = omg.get("features")
if not isinstance(features, dict):
    features = {}

features.update(get_preset_features(resolve_preset(preset)))
omg["features"] = features
omg["preset"] = resolve_preset(preset)
omg["_version"] = CANONICAL_VERSION
settings["_omg"] = omg

settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

write_native_adoption_report() {
    python3 - "$SCRIPT_DIR" "$CLAUDE_DIR" "$ADOPTION_MODE" "$ADOPT_MODE" "$OMG_PRESET" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
project_dir = Path(sys.argv[2])
mode = sys.argv[3]
adopt = sys.argv[4]
preset = sys.argv[5]

sys.path.insert(0, str(root))

from runtime.adoption import build_adoption_report, write_adoption_report

report = build_adoption_report(project_dir, requested_mode=mode, preset=preset, adopt=adopt)
path = write_adoption_report(project_dir, report)
print(path)
PY
}

apply_adoption_mode_marker() {
    if [ "$ADOPTION_MODE" = "coexist" ]; then
        if ! $DRY_RUN; then
            mkdir -p "$CLAUDE_DIR/hooks"
            printf '%s\n' "coexist" > "$CLAUDE_DIR/hooks/.omg-coexist"
        fi
        track_file "hooks/.omg-coexist"
    else
        if ! $DRY_RUN; then
            rm -f "$CLAUDE_DIR/hooks/.omg-coexist"
        fi
    fi
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
        [[ "$CLAUDE_DIR/.omg" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/.omg" >&2; exit 1; }
        rm -rf "$CLAUDE_DIR/.omg"

        [[ "$PLUGIN_CACHE_DIR" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $PLUGIN_CACHE_DIR" >&2; exit 1; }
        rm -rf "$PLUGIN_CACHE_DIR"
        [[ "$LEGACY_PLUGIN_CACHE_DIR" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $LEGACY_PLUGIN_CACHE_DIR" >&2; exit 1; }
        rm -rf "$LEGACY_PLUGIN_CACHE_DIR"
        rm -f "$CLAUDE_DIR/hud/omg-hud.mjs"
        unregister_plugin_from_registry "$PLUGIN_REF"
        unregister_plugin_from_registry "$LEGACY_PLUGIN_REF"
        unregister_plugin_marketplace "$PLUGIN_MARKETPLACE"
        remove_hud_status_line

        if $remove_plugin_managed_mcp; then
            local pruned_mcp=0
            pruned_mcp=$(prune_plugin_mcp_from_settings)
            if [ "${pruned_mcp:-0}" -gt 0 ]; then
                echo "  ✓ Plugin-managed MCP servers removed from .mcp.json ($pruned_mcp)"
            fi
        fi

        local removed_host_mcp=""
        removed_host_mcp=$(remove_detected_host_mcp_servers)
        if [ -n "$removed_host_mcp" ]; then
            echo "  ✓ Removed OMG MCP config from detected hosts: $removed_host_mcp"
        fi

        remove_omg_hooks_from_settings
        echo "  ✓ Removed OMG hook entries from settings.json (if any)"
        remove_omg_metadata_from_settings
        echo "  ✓ Removed OMG metadata from settings.json (if any)"
        remove_codex_managed_residue
        echo "  ✓ Removed Codex OMG residue (if any)"
    fi
}

install_plugin_bundle() {
    local plugin_ref="$PLUGIN_REF"
    local plugin_root="$PLUGIN_CACHE_DIR/$VERSION"
    local plugin_manifest_src="$SCRIPT_DIR/.claude-plugin/plugin.json"
    local plugin_manifest_target="$plugin_root/.claude-plugin/plugin.json"
    local marketplace_manifest_src="$SCRIPT_DIR/.claude-plugin/marketplace.json"
    local marketplace_manifest_target="$plugin_root/.claude-plugin/marketplace.json"
    local plugin_mcp_target="$plugin_root/.claude-plugin/mcp.json"
    local hud_src="$SCRIPT_DIR/hud/omg-hud.mjs"
    local hud_target="$CLAUDE_DIR/hud/omg-hud.mjs"

    echo "  Plugin bundle mode enabled: install plugin + MCP + HUD together"
    if $DRY_RUN; then
        echo "  (would install plugin bundle under $plugin_root and deploy HUD to $hud_target)"
        echo "  (would register plugin in ~/.claude/plugins/installed_plugins.json, enable it in settings.json, and add the omg marketplace)"
        echo "  (would merge plugin MCP servers into .mcp.json)"
        return 0
    fi

    mkdir -p "$plugin_root/.claude-plugin"
    mkdir -p "$CLAUDE_DIR/hud"
    cp "$plugin_manifest_src" "$plugin_manifest_target"
    if [ -f "$marketplace_manifest_src" ]; then
        cp "$marketplace_manifest_src" "$marketplace_manifest_target"
    fi
    
    # Provide a fallback plugin MCP file if not shipped in npm package.
    if [ ! -f "$SCRIPT_DIR/.claude-plugin/mcp.json" ] && [ ! -f "$SCRIPT_DIR/.mcp.json" ]; then
        local _fallback_mcp_dir
        _fallback_mcp_dir=$(mktemp -d)
        mkdir -p "$_fallback_mcp_dir/.claude-plugin"
        cat > "$_fallback_mcp_dir/.claude-plugin/mcp.json" <<'FALLBACK_MCP'
{
  "mcpServers": {
    "omg-control": {
      "command": "python3",
      "args": ["-m", "runtime.omg_mcp_server"]
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
    chmod +x "$hud_target" 2>/dev/null || true
    mkdir -p "$PLUGIN_CACHE_DIR"
    printf '%s\n' "omg-plugin-bundle-v1" > "$PLUGIN_CACHE_DIR/$PLUGIN_BUNDLE_MARKER_FILE"

    unregister_plugin_from_registry "$LEGACY_PLUGIN_REF"
    register_plugin_in_registry "$plugin_ref" "$plugin_root" "$VERSION"
    register_plugin_marketplace "$PLUGIN_MARKETPLACE" "$plugin_root"

    track_file "plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME/$VERSION/.claude-plugin/plugin.json"
    track_file "plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME/$VERSION/.claude-plugin/marketplace.json"
    track_file "plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME/$VERSION/.claude-plugin/mcp.json"
    track_file "plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME/$PLUGIN_BUNDLE_MARKER_FILE"
    track_file "hud/omg-hud.mjs"
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

    if ! $DRY_RUN; then
        local _removed_json _preserved_json _host_configs_json
        _removed_json=$(python3 -c "
import json, os, sys
d = sys.argv[1]
paths = [os.path.join(d, p) for p in ['hooks', 'rules', 'agents', 'commands', 'templates/omg', 'omg-runtime', 'hud/omg-hud.mjs', 'plugins/cache'] if not os.path.exists(os.path.join(d, p))]
print(json.dumps(paths))
" "$CLAUDE_DIR" 2>/dev/null || echo "[]")
        _preserved_json=$(python3 -c "
import json, os, sys
d = sys.argv[1]
paths = [os.path.join(d, p) for p in ['settings.json'] if os.path.exists(os.path.join(d, p))]
print(json.dumps(paths))
" "$CLAUDE_DIR" 2>/dev/null || echo "[]")
        _host_configs_json=$(python3 -c "
import json, os
home = os.path.expanduser('~')
configs = {
    'codex': os.path.join(home, '.codex', 'config.toml'),
    'gemini': os.path.join(home, '.gemini', 'settings.json'),
    'kimi': os.path.join(home, '.kimi', 'mcp.json'),
}
cleaned = []
for host, path in configs.items():
    if os.path.exists(path):
        try:
            content = open(path, encoding='utf-8').read()
            if 'omg-control' not in content:
                cleaned.append(path)
        except Exception:
            pass
    else:
        cleaned.append(path)
print(json.dumps(cleaned))
" 2>/dev/null || echo "[]")
        emit_uninstall_receipt "$_removed_json" "$_preserved_json" "$_host_configs_json"
        echo "  ✓ Uninstall receipt written to $CLAUDE_DIR/.omg-uninstall-receipt.json"
    fi

    if $VERIFY_CLEAN; then
        python3 - "$CLAUDE_DIR" "$REPAIR" "$DRY_RUN" <<'VERIFY_CLEAN_PY'
import glob
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

claude_dir = Path(sys.argv[1])
repair = sys.argv[2] == "true"
dry_run = sys.argv[3] == "true"
home = Path(os.path.expanduser("~"))


def has_codex_section(path: Path, server_name: str) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    headers = {f"[mcp_servers.{server_name}]", f'[mcp_servers."{server_name}"]'}
    return any(line.strip() in headers for line in lines)


def remove_codex_section(path: Path, server_name: str) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    headers = {f"[mcp_servers.{server_name}]", f'[mcp_servers."{server_name}"]'}
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() in headers:
            start_idx = idx
            break
    if start_idx is None:
        return False
    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break
    updated = lines[:start_idx] + lines[end_idx:]
    content = "".join(updated).lstrip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def has_json_server(path: Path, server_name: str, mcp_key: str = "mcpServers") -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    servers = data.get(mcp_key)
    return isinstance(servers, dict) and server_name in servers


def remove_json_server(path: Path, server_name: str, mcp_key: str = "mcpServers") -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    servers = data.get(mcp_key)
    if not isinstance(servers, dict) or server_name not in servers:
        return False
    servers.pop(server_name, None)
    data[mcp_key] = servers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True


def has_omg_hooks(settings_path: Path) -> bool:
    if not settings_path.exists():
        return False
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for _event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and "omg-runtime" in str(entry.get("command", "")):
                return True
    return False


def remove_omg_hooks(settings_path: Path) -> bool:
    if not settings_path.exists():
        return False
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    changed = False
    new_hooks: dict[str, object] = {}
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            new_hooks[event] = entries
            continue
        filtered = [
            e for e in entries
            if not (isinstance(e, dict) and "omg-runtime" in str(e.get("command", "")))
        ]
        if len(filtered) < len(entries):
            changed = True
        if filtered:
            new_hooks[event] = filtered
    if not changed:
        return False
    if new_hooks:
        settings["hooks"] = new_hooks
    else:
        settings.pop("hooks", None)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True


def has_omg_status_line(settings_path: Path) -> bool:
    if not settings_path.exists():
        return False
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    sl = settings.get("statusLine")
    return isinstance(sl, dict) and "omg-hud.mjs" in str(sl.get("command", ""))


def remove_omg_status_line(settings_path: Path) -> bool:
    if not settings_path.exists():
        return False
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    sl = settings.get("statusLine")
    if not (isinstance(sl, dict) and "omg-hud.mjs" in str(sl.get("command", ""))):
        return False
    settings.pop("statusLine", None)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True


audited_surfaces: list[str] = []
residue_found: list[dict[str, str]] = []
repaired_surfaces: list[dict[str, str]] = []
backed_up: set[str] = set()

file_residue_paths = [
    claude_dir / "hooks" / ".omg-version",
    claude_dir / "hooks" / ".omg-coexist",
    claude_dir / "omg-runtime",
    claude_dir / "templates" / "omg",
    claude_dir / "hud" / "omg-hud.mjs",
    claude_dir / ".omg-manifest",
]
audited_surfaces.append("claude_file_residue")
for p in file_residue_paths:
    if p.exists():
        residue_found.append({"surface": "claude_file_residue", "path": str(p)})
for pattern in [
    str(claude_dir / "rules" / "omg-*.md"),
    str(claude_dir / "rules" / "0[0-4]-*.md"),
    str(claude_dir / "agents" / "omg-*.md"),
]:
    for match in glob.glob(pattern):
        residue_found.append({"surface": "claude_file_residue", "path": match})

settings_path = claude_dir / "settings.json"

audited_surfaces.append("claude_hooks")
if has_omg_hooks(settings_path):
    residue_found.append({"surface": "claude_hooks", "path": str(settings_path)})

audited_surfaces.append("claude_status_line")
if has_omg_status_line(settings_path):
    residue_found.append({"surface": "claude_status_line", "path": str(settings_path)})

audited_surfaces.append("claude_plugin")
try:
    s = json.loads(settings_path.read_text(encoding="utf-8"))
    if "omg@omg" in (s.get("enabledPlugins") or {}):
        residue_found.append({"surface": "claude_plugin", "path": str(settings_path)})
except Exception:
    pass

codex_path = home / ".codex" / "config.toml"
audited_surfaces.append("codex_mcp")
if has_codex_section(codex_path, "omg-control"):
    residue_found.append({"surface": "codex_mcp", "path": str(codex_path)})

gemini_path = home / ".gemini" / "settings.json"
audited_surfaces.append("gemini_mcp")
if has_json_server(gemini_path, "omg-control"):
    residue_found.append({"surface": "gemini_mcp", "path": str(gemini_path)})

kimi_path = home / ".kimi" / "mcp.json"
audited_surfaces.append("kimi_mcp")
if has_json_server(kimi_path, "omg-control"):
    residue_found.append({"surface": "kimi_mcp", "path": str(kimi_path)})

opencode_path = home / ".config" / "opencode" / "opencode.json"
audited_surfaces.append("opencode_mcp")
if has_json_server(opencode_path, "omg-control", mcp_key="mcp"):
    residue_found.append({"surface": "opencode_mcp", "path": str(opencode_path)})

if repair and not dry_run and residue_found:
    def backup_once(p: Path) -> None:
        key = str(p)
        if key in backed_up or not p.exists():
            return
        bak = p.parent / (p.name + ".omg-backup")
        if p.is_dir():
            shutil.copytree(p, bak, dirs_exist_ok=True)
        else:
            shutil.copy2(p, bak)
        backed_up.add(key)

    for item in list(residue_found):
        surface = item["surface"]
        path = Path(item["path"])
        if surface == "claude_file_residue":
            if path.exists():
                backup_once(path)
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                repaired_surfaces.append(item)
        elif surface == "codex_mcp":
            backup_once(path)
            if remove_codex_section(path, "omg-control"):
                repaired_surfaces.append(item)
        elif surface in ("gemini_mcp", "kimi_mcp"):
            backup_once(path)
            if remove_json_server(path, "omg-control"):
                repaired_surfaces.append(item)
        elif surface == "opencode_mcp":
            backup_once(path)
            if remove_json_server(path, "omg-control", mcp_key="mcp"):
                repaired_surfaces.append(item)
        elif surface == "claude_hooks":
            backup_once(path)
            if remove_omg_hooks(path):
                repaired_surfaces.append(item)
        elif surface == "claude_status_line":
            backup_once(path)
            if remove_omg_status_line(path):
                repaired_surfaces.append(item)
        elif surface == "claude_plugin":
            backup_once(path)
            try:
                s = json.loads(path.read_text(encoding="utf-8"))
                ep = s.get("enabledPlugins")
                if isinstance(ep, dict) and "omg@omg" in ep:
                    ep.pop("omg@omg")
                    if not ep:
                        s.pop("enabledPlugins", None)
                    path.write_text(json.dumps(s, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
                    repaired_surfaces.append(item)
            except Exception:
                pass

repaired_set = {(r["surface"], r["path"]) for r in repaired_surfaces}
remaining_blockers = [r for r in residue_found if (r["surface"], r["path"]) not in repaired_set]
residue_surface_names = {r["surface"] for r in residue_found}
preserved_surfaces = [s for s in audited_surfaces if s not in residue_surface_names]

status = "clean" if not remaining_blockers else "residue_found"

receipt: dict[str, object] = {
    "schema": "VerifyCleanReceipt",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "verification_status": status,
    "audited_surfaces": audited_surfaces,
    "residue_found": residue_found,
    "repaired_surfaces": repaired_surfaces,
    "preserved_surfaces": preserved_surfaces,
    "remaining_blockers": remaining_blockers,
}

if not dry_run:
    receipt_path = claude_dir / ".omg-verify-clean-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

print(json.dumps(receipt, indent=2, ensure_ascii=True))
if status == "clean":
    print("  \u2713 Verify-clean: no OMG-owned residue found.", file=sys.stderr)
else:
    count = len(remaining_blockers)
    print(f"  \u2717 Verify-clean: residue found in {count} surface(s)", file=sys.stderr)
VERIFY_CLEAN_PY
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
    verify_install_integrity

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
    echo "  ✓ Command surface: /OMG:setup and /OMG:crazy are the primary native front door"
    echo "  ✓ Adoption mode: $ADOPTION_MODE"
    echo "  ✓ Preset: $OMG_PRESET"

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
    apply_adoption_mode_marker
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
            apply_omg_preset_to_settings "$TARGET" "$OMG_PRESET"
            echo "  ✓ Created settings.json"
        else
            if [ "$MERGE_POLICY" = "skip" ]; then
                apply_omg_preset_to_settings "$TARGET" "$OMG_PRESET"
                echo "  ⊘ Skipped settings merge (--merge-policy=skip)"
            elif [ "$MERGE_POLICY" = "apply" ] || $NON_INTERACTIVE; then
                python3 "$MERGE" "$TARGET" "$SOURCE"
                apply_omg_preset_to_settings "$TARGET" "$OMG_PRESET"
                echo "  ✓ Settings merged (auto)"
            else
                echo "  Merging settings.json..."
                dry_run_preview="$(python3 "$MERGE" "$TARGET" "$SOURCE" --dry-run 2>&1)"
                printf '%s\n' "$dry_run_preview" | sed -n '1,5p' | sed 's/^/      /'
                echo ""
                if read -p "  Apply merge? [Y/n] " -n 1 -r; then
                    echo ""
                    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                        python3 "$MERGE" "$TARGET" "$SOURCE"
                        apply_omg_preset_to_settings "$TARGET" "$OMG_PRESET"
                        echo "  ✓ Settings merged"
                    else
                        echo "  ⊘ Skipped (manual merge needed)"
                    fi
                else
                    # read failed — only auto-apply if we can confirm non-interactive context
                    # non-interactive fallback: check for clear non-interactive indicators
                    if [ ! -t 0 ] || [ -n "${npm_lifecycle_event:-}" ] || [ -n "${npm_execpath:-}" ]; then
                        python3 "$MERGE" "$TARGET" "$SOURCE"
                        apply_omg_preset_to_settings "$TARGET" "$OMG_PRESET"
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
            [[ "$CLAUDE_DIR/omg-runtime/plugins" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/plugins" >&2; exit 1; }
            [[ "$CLAUDE_DIR/omg-runtime/registry" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/registry" >&2; exit 1; }
            [[ "$CLAUDE_DIR/omg-runtime/tools" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/tools" >&2; exit 1; }
            [[ "$CLAUDE_DIR/omg-runtime/control_plane" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/control_plane" >&2; exit 1; }
            [[ "$CLAUDE_DIR/omg-runtime/omg_natives" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/omg_natives" >&2; exit 1; }
            [[ "$CLAUDE_DIR/omg-runtime/yaml.py" == "$CLAUDE_DIR"* ]] || { echo "ERROR: symlink target outside expected directory: $CLAUDE_DIR/omg-runtime/yaml.py" >&2; exit 1; }
            
            rm -rf "$CLAUDE_DIR/omg-runtime/runtime" "$CLAUDE_DIR/omg-runtime/hooks" "$CLAUDE_DIR/omg-runtime/lab" "$CLAUDE_DIR/omg-runtime/plugins" "$CLAUDE_DIR/omg-runtime/registry" "$CLAUDE_DIR/omg-runtime/tools" "$CLAUDE_DIR/omg-runtime/control_plane" "$CLAUDE_DIR/omg-runtime/omg_natives" "$CLAUDE_DIR/omg-runtime/yaml.py"
            ln -s "$SCRIPT_DIR/runtime" "$CLAUDE_DIR/omg-runtime/runtime"
            ln -s "$SCRIPT_DIR/hooks" "$CLAUDE_DIR/omg-runtime/hooks"
            ln -s "$SCRIPT_DIR/lab" "$CLAUDE_DIR/omg-runtime/lab"
            ln -s "$SCRIPT_DIR/plugins" "$CLAUDE_DIR/omg-runtime/plugins"
            ln -s "$SCRIPT_DIR/registry" "$CLAUDE_DIR/omg-runtime/registry"
            ln -s "$SCRIPT_DIR/tools" "$CLAUDE_DIR/omg-runtime/tools"
            ln -s "$SCRIPT_DIR/control_plane" "$CLAUDE_DIR/omg-runtime/control_plane"
            if [ -d "$SCRIPT_DIR/omg_natives" ]; then
                ln -s "$SCRIPT_DIR/omg_natives" "$CLAUDE_DIR/omg-runtime/omg_natives"
            else
                echo "  ~ omg_natives not found in package — skipping (optional)" >&2
            fi
            ln -s "$SCRIPT_DIR/yaml.py" "$CLAUDE_DIR/omg-runtime/yaml.py"
            
            [[ "$CLAUDE_DIR/omg-runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/omg-runtime" >&2; exit 1; }
            find "$CLAUDE_DIR/omg-runtime" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
            find "$CLAUDE_DIR/omg-runtime" -name "*.pyc" -delete 2>/dev/null || true
            echo "  ✓ Portable runtime → $CLAUDE_DIR/omg-runtime (symlinked to $SCRIPT_DIR)"
        else
            mkdir -p "$CLAUDE_DIR/omg-runtime/scripts"
            cp "$SCRIPT_DIR/scripts/omg.py" "$CLAUDE_DIR/omg-runtime/scripts/omg.py"
            [[ "$CLAUDE_DIR/omg-runtime/runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/omg-runtime/runtime" >&2; exit 1; }
            rm -rf "$CLAUDE_DIR/omg-runtime/runtime" "$CLAUDE_DIR/omg-runtime/hooks" "$CLAUDE_DIR/omg-runtime/lab" "$CLAUDE_DIR/omg-runtime/plugins" "$CLAUDE_DIR/omg-runtime/registry" "$CLAUDE_DIR/omg-runtime/tools" "$CLAUDE_DIR/omg-runtime/control_plane" "$CLAUDE_DIR/omg-runtime/omg_natives" "$CLAUDE_DIR/omg-runtime/yaml.py"
            cp -R "$SCRIPT_DIR/runtime" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/hooks" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/lab" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/plugins" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/registry" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/tools" "$CLAUDE_DIR/omg-runtime/"
            cp -R "$SCRIPT_DIR/control_plane" "$CLAUDE_DIR/omg-runtime/"
            if [ -d "$SCRIPT_DIR/omg_natives" ]; then
                cp -R "$SCRIPT_DIR/omg_natives" "$CLAUDE_DIR/omg-runtime/"
            else
                echo "  ~ omg_natives not found in package — skipping (optional)" >&2
            fi
            cp "$SCRIPT_DIR/yaml.py" "$CLAUDE_DIR/omg-runtime/yaml.py"
            [[ "$CLAUDE_DIR/omg-runtime" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $CLAUDE_DIR/omg-runtime" >&2; exit 1; }
            find "$CLAUDE_DIR/omg-runtime" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
            find "$CLAUDE_DIR/omg-runtime" -name "*.pyc" -delete 2>/dev/null || true
            echo "  ✓ Portable runtime → $CLAUDE_DIR/omg-runtime"
        fi
        if $INSTALL_AS_PLUGIN; then
            install_plugin_bundle
        fi

        provision_managed_venv
        write_managed_mcp_launcher
        patch_omg_control_mcp_python
        local pruned_plugin_duplicates=0
        pruned_plugin_duplicates=$(prune_plugin_duplicate_mcp_from_settings)
        if [ "${pruned_plugin_duplicates:-0}" -gt 0 ]; then
            echo "  ✓ Removed duplicate plugin-managed MCP servers from .mcp.json ($pruned_plugin_duplicates)"
        fi
        local pruned_legacy_plugin_mcp=0
        pruned_legacy_plugin_mcp=$(prune_legacy_plugin_mcp_from_settings)
        if [ "${pruned_legacy_plugin_mcp:-0}" -gt 0 ]; then
            echo "  ✓ Removed legacy plugin MCP servers from .mcp.json ($pruned_legacy_plugin_mcp)"
        fi
        configure_hud_status_line
        local configured_hosts=""
        configured_hosts=$(configure_detected_host_mcp_servers)
        if [ -n "$configured_hosts" ]; then
            echo "  ✓ Host MCP configured for detected CLIs: $configured_hosts"
        fi
        if $ENABLE_BROWSER; then
            configure_browser_capability
        fi

        local adoption_report_path=""
        adoption_report_path=$(write_native_adoption_report)
        echo "  ✓ Adoption report → $adoption_report_path"
    else
        echo "  (would merge settings.json + copy templates + provision portable runtime)"
        if $INSTALL_AS_PLUGIN; then
            install_plugin_bundle
        fi
        echo "  (would provision managed Python venv at $CLAUDE_DIR/omg-runtime/.venv)"
        echo "  (would wire omg-control into detected Codex/Gemini/Kimi configs when available)"
        if $ENABLE_BROWSER; then
            echo "  (would enable browser capability metadata and remediation)"
        fi
        echo "  (would write adoption report and apply preset/mode markers)"
    fi


    echo ""
    echo "Step 7/7: Reconcile stale files..."
    reconcile_stale_files
    write_omg_manifest

    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    if [ $ERRORS -eq 0 ]; then
        echo "  ✅ OMG ${VERSION} ${ACTION} completed successfully"
    else
        echo "  ⚠  OMG ${VERSION} ${ACTION} completed with $ERRORS error(s)"
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
    # --- Post-install validation (runs AFTER all setup writes complete) ---
    echo ""
    echo "Post-install validation..."
    local validate_output=""
    local validate_rc=0
    if [ -n "${OMG_TEST_POST_INSTALL_VALIDATE_OUTPUT:-}" ]; then
        validate_output="${OMG_TEST_POST_INSTALL_VALIDATE_OUTPUT}"
        validate_rc="${OMG_TEST_POST_INSTALL_VALIDATE_RC:-1}"
    else
        validate_output=$(python3 "$SCRIPT_DIR/scripts/omg.py" validate --format json 2>&1) || validate_rc=$?
    fi

    if ! $DRY_RUN && [ -n "$validate_output" ]; then
        mkdir -p "$CLAUDE_DIR/.omg/state"
        printf '%s\n' "$validate_output" > "$CLAUDE_DIR/.omg/state/post-install-validation.json"
    fi

    if [ $validate_rc -eq 0 ]; then
        echo "  ✅ Post-install validation passed"
        if ! $DRY_RUN; then
            echo "  ✓ Artifact → $CLAUDE_DIR/.omg/state/post-install-validation.json"
        fi
    else
        echo "  ❌ POST-INSTALL VALIDATION FAILED"
        echo ""
        printf '%s' "$validate_output" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    blockers = [c for c in data.get('checks', []) if c.get('status') == 'blocker']
    if blockers:
        print('  Blockers:')
        for b in blockers:
            print(f'    - {b[\"name\"]}: {b[\"message\"]}')
    else:
        print('  (no blocker details available)')
except Exception:
    print('  (could not parse validation output)')
" 2>/dev/null
        echo ""
        if ! $DRY_RUN; then
            echo "  Validation artifact: $CLAUDE_DIR/.omg/state/post-install-validation.json"
        fi
        echo "  Run: python3 $SCRIPT_DIR/scripts/omg.py validate"
        exit 1
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
