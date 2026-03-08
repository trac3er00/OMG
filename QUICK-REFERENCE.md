# OMG CLI Adapter Quick Reference

## 🎯 Core Integration Points

### Config Writers (mcp_config_writers.py)
```python
# Claude Code (JSON)
write_claude_mcp_config(project_dir, server_url, server_name="memory-server")
write_claude_mcp_stdio_config(project_dir, *, command, args, server_name="omg-control")

# Codex (TOML)
write_codex_mcp_config(server_url, server_name="memory-server", config_path=None)
write_codex_mcp_stdio_config(*, command, args, server_name="omg-control", config_path=None)

# Gemini (JSON)
write_gemini_mcp_config(server_url, server_name="memory-server", config_path=None)
write_gemini_mcp_stdio_config(*, command, args, server_name="omg-control", config_path=None)

# Kimi (JSON)
write_kimi_mcp_config(server_url, server_name="memory-server", config_path=None)
write_kimi_mcp_stdio_config(*, command, args, server_name="omg-control", config_path=None)
```

### Install Methods
| Target | Config File | Plugin Registry | Detection |
|--------|------------|-----------------|-----------|
| Claude | `.mcp.json` | `~/.claude/plugins/installed_plugins.json` + `~/.claude/plugins/known_marketplaces.json` | Default (N/A) |
| Codex | `~/.codex/config.toml` | N/A | `which codex` |
| Gemini | `~/.gemini/settings.json` | N/A | `which gemini` |
| Kimi | `~/.kimi/mcp.json` | N/A | `which kimi` |

---

## 🚨 Critical Failure Modes

### 1. **TOML Parser Failure (Codex)**
- **Location:** `write_codex_mcp_config()` line 117-139
- **Risk:** Regex-based section matching can fail if TOML has unusual formatting
- **Mitigation:** Validate section header detection before write

### 2. **JSON Malformation (Gemini, Kimi, Claude)**
- **Location:** `_load_json()` line 22-31
- **Risk:** If existing JSON is invalid, silently returns empty dict (loses data)
- **Mitigation:** Add validation before overwriting; preserve backups

### 3. **Atomic Write Interrupted**
- **Location:** `_atomic_write_text()` line 15-19
- **Risk:** If process killed between temp write and rename, file incomplete
- **Mitigation:** Verify file integrity after write; use fsync on critical files

### 4. **Missing Python 3.10+**
- **Location:** `OMG-setup.sh` line 272-277
- **Risk:** fastmcp >=2.0 requires Python 3.10+; precheck fails
- **Mitigation:** Document Python version requirement prominently

### 5. **PATH Not Updated After Install**
- **Location:** Provider `detect()` methods use `shutil.which()`
- **Risk:** If CLI installed in shell session but PATH not refreshed, detection fails
- **Mitigation:** Document shell restart requirement; add explicit PATH check

### 6. **Plugin Cache Dir Not Created**
- **Location:** `register_plugin_in_registry()` line 626
- **Risk:** If `mkdir -p` fails (permissions), registry entry created but files missing
- **Mitigation:** Verify cache dir exists before plugin registration

### 7. **Marketplace Registration Missing (Claude Code)**
- **Location:** plugin bundle install path
- **Risk:** Claude reports `Plugin 'omg' not found in marketplace 'omg'`
- **Mitigation:** Ensure `~/.claude/plugins/known_marketplaces.json` contains the local `omg` directory marketplace

---

## 📋 Installation Verification Steps

### For Each Target:
1. **Binary Detection**
   - Claude: Skip (default)
   - Codex/Gemini/Kimi: `which <binary>`

2. **Auth Check**
   - Claude: Skip (implicit)
   - Codex: `codex auth status`
   - Gemini: `gemini auth status`
   - Kimi: Check `~/.kimi/config.toml` for token

3. **Config File**
   - Verify file exists
   - Validate file format (JSON/TOML)
   - Check MCP server entry present

4. **Plugin Registry** (Claude only)
   - `enabledPlugins["omg@omg"]` in settings.json
   - Entry in installed_plugins.json
   - Entry in known_marketplaces.json

5. **Runtime**
   - `~/.claude/omg-runtime/` or venv exists
   - Python path points to correct interpreter

---

## 🔧 Commands by Target

### Claude Code
```bash
# Install
npm install @trac3er/oh-my-god
# or
git clone https://github.com/trac3er00/OMG && cd OMG && ./OMG-setup.sh install --preset=balanced

# Verify
cat ~/.claude/plugins/cache/omg/omg/2.1.0/.claude-plugin/mcp.json | jq .mcpServers
cat ~/.claude/settings.json | jq .enabledPlugins
cat ~/.claude/settings.json | jq .statusLine
cat ~/.claude/plugins/known_marketplaces.json | jq .

# Run
/OMG:setup
/OMG:crazy <goal>
```

### Codex
```bash
# Install
npm install @trac3er/oh-my-god
./OMG-setup.sh install --preset=interop

# Verify
codex mcp list
grep "\[mcp_servers" ~/.codex/config.toml
codex auth status

# Notes
# Claude slash commands do not exist in Codex CLI.
```

### Gemini
```bash
# Detect
which gemini && gemini auth status

# Verify
gemini mcp list
cat ~/.gemini/settings.json | jq .mcpServers
```

### Kimi
```bash
# Detect
which kimi && grep token ~/.kimi/config.toml

# Verify
kimi mcp list
cat ~/.kimi/mcp.json | jq .mcpServers
```

---

## 🏗️ File Structure After Install

```
~/.claude/
├── .mcp.json                          # Shared MCP config (de-duplicated from plugin-managed servers)
├── plugins/
│   ├── cache/omg/omg/2.1.0/
│   │   ├── .claude-plugin/plugin.json
│   │   ├── .claude-plugin/marketplace.json
│   │   ├── .claude-plugin/mcp.json
│   │   └── .omg-plugin-bundle
│   └── installed_plugins.json         # Registry
│   └── known_marketplaces.json        # Marketplace resolution
├── settings.json                      # enabledPlugins + statusLine
├── hud/omg-hud.mjs                   # UI component
├── omg-runtime/                       # Portable runtime
│   ├── runtime/
│   ├── hooks/
│   ├── plugins/
│   ├── scripts/
│   ├── .venv/                        # Managed Python venv
│   └── yaml.py
├── hooks/                            # Standalone hooks
├── agents/                           # Agent definitions
├── commands/                         # Command definitions
├── rules/                            # Contextual rules
└── templates/omg/                    # Templates + state

~/.codex/
└── config.toml                        # [mcp_servers.omg-control]

~/.gemini/
└── settings.json                      # mcpServers

~/.kimi/
└── mcp.json                           # mcpServers
```

---

## 📊 Preset Feature Matrix

| Preset | Setup | Memory | Analytics | Context | Cost | GIT | Tests | Deps | Viz |
|--------|-------|--------|-----------|---------|------|-----|-------|------|-----|
| safe | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| balanced | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| interop | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| labs | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 🐛 Debugging Checklist

- [ ] `echo $CLAUDE_CONFIG_DIR` (check path)
- [ ] `python3 --version` (>= 3.10 required)
- [ ] `which codex` / `which gemini` / `which kimi` (if multi-host)
- [ ] `ls -la ~/.claude/plugins/cache/omg/omg/2.1.0/.claude-plugin/mcp.json` (exists and readable)
- [ ] `cat ~/.claude/plugins/cache/omg/omg/2.1.0/.claude-plugin/mcp.json | python3 -m json.tool` (valid JSON)
- [ ] `cat ~/.claude/settings.json | jq .statusLine` (HUD command configured)
- [ ] `which npm` && `npm list @trac3er/oh-my-god` (package installed)
- [ ] `ls -la ~/.claude/omg-runtime/.venv/bin/python` (venv exists)
- [ ] Check `.omg/` directory for adoption report and errors
- [ ] Run `claude plugin list` and confirm `omg@omg` is enabled
- [ ] Review `~/.claude/hooks/.omg-version` (version marker)
