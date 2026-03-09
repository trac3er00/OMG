# OMG CLI Adapter/Integration Installer & Config Writer Map

## Executive Summary
OMG supports 4 canonical CLI targets with dedicated provider implementations and config writers. Plugin bundle installation, marketplace integration, and MCP registration are handled by the setup shell script with atomic file operations.

---

## 1. CLI PROVIDER IMPLEMENTATIONS

### A. Claude Code (Canonical)
**File:** `runtime/providers/claude.py` (stub adapter only)
**Config Writer:** `runtime/mcp_config_writers.py::write_claude_mcp_config()`
**Config Writer (stdio):** `runtime/mcp_config_writers.py::write_claude_mcp_stdio_config()`

- **Detection:** Binary not auto-detected (Claude is the default host)
- **Auth Check:** N/A (implicit via plugin installation)
- **Config Path:** `.mcp.json` in project root
- **MCP Format:** JSON with `mcpServers` object
  ```json
  {
    "mcpServers": {
      "omg-control": {
        "command": "python3",
        "args": ["-m", "runtime.omg_mcp_server"]
      },
      "filesystem": {
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem@2026.1.14", "."]
      }
    }
  }
  ```
- **CLAUDE_CONFIG_DIR:** `~/.claude` (env var override)
- **Install Method:** Plugin bundle + .mcp.json merge
- **Install Doc:** `docs/install/claude-code.md`

### B. Codex (Canonical)
**File:** `runtime/providers/codex_provider.py`
**Class:** `CodexProvider`
**Config Writer:** `runtime/mcp_config_writers.py::write_codex_mcp_config()`
**Config Writer (stdio):** `runtime/mcp_config_writers.py::write_codex_mcp_stdio_config()`

- **Detection:** `shutil.which("codex")` checks PATH
- **Auth Check:** `codex auth status` command
- **Config Path:** `~/.codex/config.toml`
- **MCP Format:** TOML with `[mcp_servers.SERVER_NAME]` sections
  ```toml
  [mcp_servers.omg-control]
  command = "python3"
  args = ["-m", "runtime.omg_mcp_server"]
  ```
- **Write Strategy:** 
  - Loads existing TOML (if present)
  - Finds or creates `[mcp_servers.SERVER_NAME]` header
  - Appends or updates block atomically via `_atomic_write_text()`
- **Invocation:** `codex exec --json <prompt>`
- **Invocation (tmux):** Via `TmuxSessionManager` session persistence
- **Install Method:** Plugin bundle + MCP merge
- **Install Doc:** `docs/install/codex.md`
- **Preset Recommendation:** `interop` (multi-host workflow)

### C. Gemini CLI (Compatibility)
**File:** `runtime/providers/gemini_provider.py`
**Class:** `GeminiProvider`
**Config Writer:** `runtime/mcp_config_writers.py::write_gemini_mcp_config()`
**Config Writer (stdio):** `runtime/mcp_config_writers.py::write_gemini_mcp_stdio_config()`

- **Detection:** `shutil.which("gemini")` checks PATH
- **Auth Check:** `gemini auth status` command
- **Config Path:** `~/.gemini/settings.json`
- **MCP Format:** JSON with `mcpServers` object
  ```json
  {
    "mcpServers": {
      "omg-control": {
        "command": "python3",
        "args": ["-m", "runtime.omg_mcp_server"]
      }
    }
  }
  ```
- **Invocation:** `gemini -p <prompt>` (no --json flag, plain text output)
- **Invocation (tmux):** Via `TmuxSessionManager` session persistence
- **HOST_RULES** (from file):
  - `compilation_targets`: `[".gemini/settings.json"]`
  - `mcp`: `["omg-control"]`
  - `skills`: `["omg/control-plane", "omg/mcp-fabric"]`
  - `automations`: `["contract-validate", "provider-routing"]`

### D. Kimi Code CLI (Compatibility)
**File:** `runtime/providers/kimi_provider.py`
**Class:** `KimiCodeProvider`
**Config Writer:** `runtime/mcp_config_writers.py::write_kimi_mcp_config()`
**Config Writer (stdio):** `runtime/mcp_config_writers.py::write_kimi_mcp_stdio_config()`

- **Detection:** `shutil.which("kimi")` checks PATH
- **Auth Check:** Parses `~/.kimi/config.toml` for `token` entry
- **Config Path:** `~/.kimi/mcp.json`
- **MCP Format:** JSON with `mcpServers` object (type: "http", url: string)
  ```json
  {
    "mcpServers": {
      "omg-control": {
        "type": "http",
        "url": "http://localhost:3000"
      }
    }
  }
  ```
- **Invocation:** `kimi --print -p <prompt>`
- **Invocation (JSON):** `kimi --print --output-format stream-json -p <prompt>`
- **Invocation (tmux):** Via `TmuxSessionManager` session persistence
- **HOST_RULES** (from file):
  - `compilation_targets`: `[".kimi/mcp.json"]`
  - `mcp`: `["omg-control"]`
  - `skills`: `["omg/control-plane", "omg/mcp-fabric"]`
  - `automations`: `["contract-validate", "provider-routing"]`

---

## 2. CONFIG WRITER FUNCTIONS (Core Integration Points)

**File:** `runtime/mcp_config_writers.py` (233 lines)

### Functions for Each Target

| Function | Target | Format | Config Location | Special Notes |
|----------|--------|--------|-----------------|---------------|
| `write_claude_mcp_config(project_dir, server_url, server_name="memory-server")` | Claude | JSON | `.mcp.json` (project root) | HTTP-only server type |
| `write_claude_mcp_stdio_config(project_dir, *, command, args, server_name="omg-control")` | Claude | JSON | `.mcp.json` (project root) | Stdio server type |
| `write_codex_mcp_config(server_url, server_name="memory-server", config_path=None)` | Codex | TOML | `~/.codex/config.toml` | Header + block replacement |
| `write_codex_mcp_stdio_config(*, command, args, server_name="omg-control", config_path=None)` | Codex | TOML | `~/.codex/config.toml` | Header + block replacement |
| `write_gemini_mcp_config(server_url, server_name="memory-server", config_path=None)` | Gemini | JSON | `~/.gemini/settings.json` | `mcpServers` with `httpUrl` field |
| `write_gemini_mcp_stdio_config(*, command, args, server_name="omg-control", config_path=None)` | Gemini | JSON | `~/.gemini/settings.json` | Command + args array |
| `write_kimi_mcp_config(server_url, server_name="memory-server", config_path=None)` | Kimi | JSON | `~/.kimi/mcp.json` | Type + URL standard |
| `write_kimi_mcp_stdio_config(*, command, args, server_name="omg-control", config_path=None)` | Kimi | JSON | `~/.kimi/mcp.json` | Command + args array |

### Shared Utilities
- `get_managed_python_path(claude_config_dir=None)` → Path to managed venv Python interpreter
- `_atomic_write_text(path, content)` → Atomic file write with temp file + rename
- `_load_json(path)` → Safe JSON load with fallback to empty dict
- `_write_json(path, data)` → Atomic JSON write
- `_validated_server_input(server_url, server_name)` → Validate and quote server URL/name
- `_validated_stdio_input(command, args, server_name)` → Validate command, args (no newlines)
- `_write_json_mcp_server(path, server_name, payload)` → Merge MCP server into JSON config

---

## 3. PLUGIN BUNDLE INSTALLATION (OMG-setup.sh)

**File:** `OMG-setup.sh` (1333 lines)

### Plugin Registry & Installation Functions

#### A. Detection
- `is_standalone_installed()` → Checks for `.omg-version` or `omg-runtime/` dir
- `is_plugin_installed()` → Checks marker file or `installed_plugins.json`

#### B. Plugin Registration (Lines 570-629)
- **Function:** `register_plugin_in_registry(plugin_ref, install_path, version)`
- **Outputs:**
  - `~/.claude/settings.json` → `enabledPlugins[plugin_ref] = true`
  - `~/.claude/plugins/installed_plugins.json` → Plugin metadata with installed path, version, timestamp
- **Plugin Ref Format:** `omg@omg` (name@marketplace_id)
- **Version:** `2.1.1` (from package.json)

#### C. Plugin Unregistration (Lines 631-669)
- **Function:** `unregister_plugin_from_registry(plugin_ref)`
- **Removes:** Entry from `enabledPlugins` and `plugins` registry

#### D. Plugin Bundle Installation (Lines 820-878)
- **Function:** `install_plugin_bundle()`
- **Files Copied:**
  - `$SCRIPT_DIR/.claude-plugin/plugin.json` → `$PLUGIN_CACHE_DIR/$VERSION/.claude-plugin/plugin.json`
  - `$SCRIPT_DIR/hud/omg-hud.mjs` → `~/.claude/hud/omg-hud.mjs`
  - MCP config → `$PLUGIN_CACHE_DIR/$VERSION/.mcp.json`
- **Marker File:** `.omg-plugin-bundle` in cache dir
- **MCP Merge:** `merge_plugin_mcp_into_settings()` merges plugin's `.mcp.json` into `~/.claude/.mcp.json`
- **Fallback MCP:** If no `.mcp.json` shipped, generates default with `filesystem` + `omg-control`

### MCP Configuration Writers (within setup.sh)

#### `merge_plugin_mcp_into_settings()` (Lines 501-541)
- Reads `~/.claude/.mcp.json` and `$SCRIPT_DIR/.mcp.json`
- Merges `mcpServers` entries from source into target
- Atomic JSON write
- **Returns:** Count of merged servers

#### `write_plugin_mcp_file()` (Lines 543-568)
- Copies MCP config to plugin cache directory
- Creates plugin-specific `.mcp.json` at `$PLUGIN_CACHE_DIR/$VERSION/.mcp.json`
- Atomic JSON write
- **Returns:** Count of MCP servers written

#### `prune_plugin_mcp_from_settings()` (Lines 466-499)
- Removes plugin-managed MCP servers from `~/.claude/.mcp.json`
- Removes keys: `context7`, `filesystem`, `websearch`, `chrome-devtools`
- **Returns:** Count of removed entries

---

## 4. MARKETPLACE & REGISTRY INTEGRATION

### Package.json Integration
**File:** `package.json`
```json
{
  "name": "@trac3er/oh-my-god",
  "version": "2.1.0",
  "scripts": {
    "postinstall": "./OMG-setup.sh install --non-interactive",
    "update": "./OMG-setup.sh update",
    "uninstall": "./OMG-setup.sh uninstall"
  }
}
```

- **npm install hook:** `postinstall` triggers `./OMG-setup.sh install --non-interactive`
- **Auto-plugin mode:** npm lifecycle detected → `INSTALL_AS_PLUGIN=true`
- **CI/automation context detection:** `$npm_lifecycle_event` or `$npm_execpath` set → `NON_INTERACTIVE=true`

### Plugin Marketplace Metadata
**Constants (OMG-setup.sh, Lines 10-16):**
```bash
PLUGIN_NAME="omg"
PLUGIN_MARKETPLACE="omg"
LEGACY_PLUGIN_MARKETPLACE="oh-advanced-layer"
PLUGIN_REF="${PLUGIN_NAME}@${PLUGIN_MARKETPLACE}"
LEGACY_PLUGIN_REF="${PLUGIN_NAME}@${LEGACY_PLUGIN_MARKETPLACE}"
PLUGIN_CACHE_DIR="$CLAUDE_DIR/plugins/cache/$PLUGIN_MARKETPLACE/$PLUGIN_NAME"
```

### Adoption Constants
**File:** `runtime/adoption.py`
```python
CANONICAL_BRAND = "OMG"
CANONICAL_REPO_URL = "https://github.com/trac3er00/OMG"
CANONICAL_PACKAGE_NAME = "@trac3er/oh-my-god"
CANONICAL_PLUGIN_ID = "omg"
CANONICAL_MARKETPLACE_ID = "omg"
CANONICAL_VERSION = "2.1.1"
```

---

## 5. INSTALL COMMANDS & PATHS (by Target)

### Installation Entry Points

| Target | Fast Path | Manual Path | Preset | Mode |
|--------|-----------|-------------|--------|------|
| **Claude Code** | `npm install @trac3er/oh-my-god` | `git clone + ./OMG-setup.sh install --mode=omg-only --preset=balanced` | `balanced` | `omg-only` |
| **Codex** | `npm install @trac3er/oh-my-god` | `git clone + ./OMG-setup.sh install --mode=omg-only --preset=interop` | `interop` | `omg-only` |
| **Gemini** | Not documented | Via provider registry detect + setup | N/A | Via adoption |
| **Kimi** | Not documented | Via provider registry detect + setup | N/A | Via adoption |

### OMG-setup.sh Main Actions
```bash
./OMG-setup.sh <action> [OPTIONS]

Actions:
  install      Install or upgrade OMG components
  update       Explicit update mode
  reinstall    Clean reinstall
  uninstall    Remove OMG files

Key Options:
  --install-as-plugin   Install as plugin bundle (Claude plugin system)
  --mode=omg-only|coexist  Adoption mode
  --preset=safe|balanced|interop|labs  Feature set
  --merge-policy=ask|apply|skip  Settings merge behavior
```

---

## 6. CRITICAL ASSUMPTIONS & BREAKAGE POINTS

### Path Assumptions
1. **`$CLAUDE_CONFIG_DIR`** (default: `~/.claude`)
   - **Risk:** If env var is set to non-existent dir → plugin install fails silently
   - **Assumption:** Unix home directory structure exists
   
2. **`~/.codex/config.toml`**
   - **Risk:** If TOML parser fails or file is corrupted → MCP config not written
   - **Assumption:** TOML file can be parsed line-by-line with regex section matching

3. **`~/.gemini/settings.json` and `~/.kimi/mcp.json`**
   - **Risk:** If JSON is malformed → entire config can be lost (before safety patch)
   - **Assumption:** JSON is valid and properly formatted

### Atomic Write Assumptions
- **`_atomic_write_text()`** uses `os.replace()` (atomic on POSIX)
- **Risk:** On Windows, `os.replace()` may not be fully atomic if interrupted
- **Assumption:** Filesystem supports atomic rename

### Provider Detection Assumptions
- **`shutil.which()`** searches PATH
- **Risk:** If CLI binary is in non-standard location or PATH is corrupted → detection fails
- **Assumption:** Binary is installed and in PATH

### Python Version Requirement
- **Preflight check (OMG-setup.sh, Line 272-277):** Python 3.10+ required
- **Risk:** fastmcp >=2.0 dependency requires Python 3.10+
- **Assumption:** System has compatible Python 3 available

### npm Lifecycle Detection
- **Condition:** If `$npm_lifecycle_event` or `$npm_execpath` is set → auto-enable plugin mode
- **Risk:** May incorrectly trigger plugin mode in CI systems with npm env vars
- **Assumption:** npm environment variables accurately indicate npm invocation context

### Settings Merge Assumptions
- **`settings-merge.py` script must exist** at `$SCRIPT_DIR/scripts/settings-merge.py`
- **Risk:** If script missing → settings.json merge silently skipped or fails
- **Assumption:** Script is present and executable

### Manifest File Assumptions (Lines 425-458)
- **`$OMG_MANIFEST` file** tracks installed files for cleanup
- **Risk:** If manifest corrupted or out-of-sync → stale files may not be cleaned
- **Assumption:** Manifest is accurate and parseable (one file per line)

### Symlink Mode Assumptions
- **`--symlink` flag** creates symlinks instead of copies (dev mode)
- **Risk:** If source repo is deleted or moved → symlinks break
- **Assumption:** Repository remains at same path during development

### Venv Python Path Assumptions
- **`patch_omg_control_mcp_python()` (Line 301-331)** updates `.mcp.json` command from `python3` to venv path
- **Risk:** If venv Python path changes or venv is deleted → MCP server won't start
- **Assumption:** Venv is installed and Python at patched path exists

---

## 7. VERIFICATION CHECKLIST FOR EACH TARGET

### Claude Code
- [ ] `.mcp.json` exists in project root with `omg-control` + `filesystem` servers
- [ ] `~/.claude/plugins/installed_plugins.json` has `omg@omg` entry
- [ ] `~/.claude/settings.json` has `enabledPlugins["omg@omg"] = true`
- [ ] `~/.claude/hud/omg-hud.mjs` installed
- [ ] `~/.claude/omg-runtime/` has hooks, runtime, plugins dirs
- [ ] Run `/OMG:setup` command works
- [ ] `.omg/state/adoption-report.json` generated if existing plugins detected

### Codex
- [ ] `~/.codex/config.toml` has `[mcp_servers.omg-control]` section
- [ ] `codex auth status` returns authenticated
- [ ] `~/.claude/.mcp.json` merged with Codex MCP config (if coexist mode)
- [ ] `/OMG:setup` command executes and detects `codex` CLI
- [ ] `.codex/` skills directory configured if applicable

### Gemini
- [ ] `~/.gemini/settings.json` has `mcpServers["omg-control"]`
- [ ] `gemini auth status` returns authenticated
- [ ] Host rules met: compilation_targets, mcp, skills, automations
- [ ] Provider detected via `shutil.which("gemini")`

### Kimi
- [ ] `~/.kimi/mcp.json` has `mcpServers["omg-control"]`
- [ ] `~/.kimi/config.toml` has valid token
- [ ] Provider detected via `shutil.which("kimi")`
- [ ] Host rules met: compilation_targets, mcp, skills, automations

---

## 8. KEY FILES REFERENCE

| File | Purpose | Lines |
|------|---------|-------|
| `OMG-setup.sh` | Main installation orchestrator | 1333 |
| `runtime/mcp_config_writers.py` | Config writer functions for all targets | 233 |
| `runtime/providers/codex_provider.py` | Codex CLI integration | 102 |
| `runtime/providers/gemini_provider.py` | Gemini CLI integration | 116 |
| `runtime/providers/kimi_provider.py` | Kimi CLI integration | 139 |
| `runtime/cli_provider.py` | Abstract CLIProvider base class | 85 |
| `runtime/adoption.py` | Brand, version, preset constants | 220 |
| `package.json` | npm postinstall hook entry point | 35 |
| `OMG_COMPAT_CONTRACT.md` | Host compilation rules contract | 105 |
| `docs/install/claude-code.md` | Claude Code install guide | 31 |
| `docs/install/codex.md` | Codex install guide | 29 |

