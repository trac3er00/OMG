# OMG Install Process Verification Index

**Purpose:** Track all CLI adapter integration points, installation flows, and critical assumptions for end-to-end verification.

**Created:** 2026-03-08  
**Version:** OMG 2.1.0  
**Status:** Ready for verification and fixing

---

## 📖 Documentation Map

### Primary References
- **`CLI-ADAPTER-MAP.md`** (380 lines)
  - Complete technical specification
  - All provider implementations, config writers, and registration flows
  - Critical assumptions and failure modes
  - Verification checklists per target
  - Line-number references to source files

- **`QUICK-REFERENCE.md`** (6.7 KB)
  - Quick lookup tables and commands
  - Failure mode diagnosis
  - Debugging checklist
  - Installation verification steps

### Source Files Referenced
- `runtime/mcp_config_writers.py` (233 lines) - Config writer functions
- `runtime/providers/codex_provider.py` (102 lines)
- `runtime/providers/gemini_provider.py` (116 lines)
- `runtime/providers/kimi_provider.py` (139 lines)
- `OMG-setup.sh` (1333 lines) - Installation orchestrator
- `runtime/adoption.py` (220 lines) - Constants
- `package.json` - npm integration
- `docs/install/claude-code.md` & `docs/install/codex.md`

---

## 🎯 Installation Targets & Methods

### Canonical Targets
1. **Claude Code**
   - **Install:** `npm install @trac3er/oh-my-god` (postinstall hook)
   - **Config:** `.mcp.json` (project root)
   - **Registry:** `~/.claude/plugins/installed_plugins.json`
   - **Preset:** `balanced` (recommended)
   - **Detection:** Default (no detection needed)

2. **Codex**
   - **Install:** `npm install @trac3er/oh-my-god` + manual setup
   - **Config:** `~/.codex/config.toml` ([mcp_servers.omg-control])
   - **Registry:** Shared with Claude
   - **Preset:** `interop` (recommended)
   - **Detection:** `which codex` + `codex auth status`

### Compatibility Targets
3. **Gemini**
   - **Install:** Via provider detection during `/OMG:setup`
   - **Config:** `~/.gemini/settings.json` (mcpServers)
   - **Registry:** None (standalone)
   - **Detection:** `which gemini` + `gemini auth status`

4. **Kimi**
   - **Install:** Via provider detection during `/OMG:setup`
   - **Config:** `~/.kimi/mcp.json` (mcpServers)
   - **Registry:** None (standalone)
   - **Detection:** `which kimi` + token check

---

## 🔧 Config Writer Functions Summary

| Function | Target | Format | Location | Input Validation |
|----------|--------|--------|----------|------------------|
| `write_claude_mcp_config()` | Claude | JSON | `.mcp.json` | Server URL + name |
| `write_claude_mcp_stdio_config()` | Claude | JSON | `.mcp.json` | Command + args |
| `write_codex_mcp_config()` | Codex | TOML | `~/.codex/config.toml` | Server URL + name |
| `write_codex_mcp_stdio_config()` | Codex | TOML | `~/.codex/config.toml` | Command + args |
| `write_gemini_mcp_config()` | Gemini | JSON | `~/.gemini/settings.json` | Server URL + name |
| `write_gemini_mcp_stdio_config()` | Gemini | JSON | `~/.gemini/settings.json` | Command + args |
| `write_kimi_mcp_config()` | Kimi | JSON | `~/.kimi/mcp.json` | Server URL + name |
| `write_kimi_mcp_stdio_config()` | Kimi | JSON | `~/.kimi/mcp.json` | Command + args |

**Shared Utilities:**
- `get_managed_python_path()` - Returns venv Python path
- `_atomic_write_text()` - Atomic file write (temp + rename)
- `_load_json()` - Safe JSON load with fallback
- `_validated_server_input()` - URL/name validation
- `_validated_stdio_input()` - Command/args validation

---

## 🚨 Critical Assumptions & Failure Modes

### 1. Atomic Writes (CRITICAL)
- **Implementation:** `_atomic_write_text()` uses `os.replace()`
- **Risk Level:** HIGH
- **Platform:** Fully atomic on POSIX; not guaranteed on Windows
- **Mitigation:** 
  - [ ] Verify file integrity after write on all platforms
  - [ ] Use fsync on critical config files
  - [ ] Implement backup + restore on write failure

### 2. JSON Validation (DATA LOSS RISK)
- **Implementation:** `_load_json()` silently returns `{}` on invalid JSON
- **Risk Level:** CRITICAL
- **Scenario:** Existing config malformed → overwritten with empty config
- **Mitigation:**
  - [ ] Validate existing JSON before load
  - [ ] Create backups before any write
  - [ ] Log warnings on validation failures
  - [ ] Provide recovery mechanism

### 3. TOML Parser Robustness (Codex-specific)
- **Implementation:** Section header matching via regex (lines 117-139)
- **Risk Level:** MEDIUM
- **Scenarios:** Non-standard TOML formatting, duplicate headers
- **Mitigation:**
  - [ ] Use proper TOML parser instead of regex
  - [ ] Validate section detection before write
  - [ ] Test with malformed TOML files

### 4. Python Version Requirement
- **Requirement:** Python 3.10+ (fastmcp >=2.0)
- **Risk Level:** HIGH
- **Detection:** Preflight check in `OMG-setup.sh` (line 272-277)
- **Mitigation:**
  - [ ] Prominently document requirement
  - [ ] Provide helpful error message with upgrade link
  - [ ] Test on Python 3.9 and below

### 5. Provider Binary Detection
- **Implementation:** `shutil.which()` searches PATH
- **Risk Level:** MEDIUM
- **Scenarios:** Binary installed but PATH not refreshed; non-standard location
- **Mitigation:**
  - [ ] Document PATH refresh requirement
  - [ ] Provide explicit binary location override option
  - [ ] Check common installation paths as fallback

### 6. Plugin Registry Consistency
- **Implementation:** Two-file system (settings.json + installed_plugins.json)
- **Risk Level:** MEDIUM
- **Scenarios:** One file written, other fails; out-of-sync state
- **Mitigation:**
  - [ ] Use transactional writes or rollback mechanism
  - [ ] Validate both files after registration
  - [ ] Provide cleanup tool for stale entries

### 7. Manifest File Accuracy
- **Implementation:** Manifest tracks installed files for cleanup
- **Risk Level:** MEDIUM
- **Scenarios:** Manifest corrupted; files added outside installer
- **Mitigation:**
  - [ ] Validate manifest format before use
  - [ ] Rebuild manifest if corrupted
  - [ ] Compare manifest against actual files

### 8. Settings Merge Script
- **Implementation:** `scripts/settings-merge.py` must exist
- **Risk Level:** MEDIUM
- **Scenarios:** Script missing; script has errors
- **Mitigation:**
  - [ ] Verify script existence before calling
  - [ ] Provide inline merge logic as fallback
  - [ ] Test merge logic with various settings.json formats

### 9. Venv Python Path Persistence
- **Implementation:** `patch_omg_control_mcp_python()` updates .mcp.json
- **Risk Level:** MEDIUM
- **Scenarios:** Venv deleted; path changes after install
- **Mitigation:**
  - [ ] Store venv path in durable config
  - [ ] Implement venv regeneration on missing interpreter
  - [ ] Add health check on startup

### 10. npm Environment Detection
- **Implementation:** Check `$npm_lifecycle_event` and `$npm_execpath`
- **Risk Level:** LOW
- **Scenarios:** CI systems set npm env vars unexpectedly
- **Mitigation:**
  - [ ] Test in various CI systems (GitHub Actions, GitLab CI, etc.)
  - [ ] Provide explicit --install-as-plugin flag override
  - [ ] Document CI-specific setup requirements

---

## ✅ Verification Checklist

### Pre-Install Validation
- [ ] Python 3.10+ available (`python3 --version`)
- [ ] npm installed (if using npm install)
- [ ] Disk space available (~100 MB for runtime)
- [ ] File write permissions in home directory
- [ ] Git installed (for clone method)

### Claude Code Installation
- [ ] `npm install @trac3er/oh-my-god` completes without error
- [ ] `.mcp.json` created in project root
- [ ] `.mcp.json` contains `omg-control` and `filesystem` servers
- [ ] `.mcp.json` valid JSON (`python3 -m json.tool` succeeds)
- [ ] `~/.claude/plugins/installed_plugins.json` has `omg@omg` entry
- [ ] `~/.claude/settings.json` has `enabledPlugins["omg@omg"] = true`
- [ ] `~/.claude/hud/omg-hud.mjs` installed
- [ ] `~/.claude/omg-runtime/` contains hooks, runtime, plugins
- [ ] `~/.claude/omg-runtime/.venv/bin/python` exists and executable
- [ ] `/OMG:setup` command available and executes without error
- [ ] `.omg/state/adoption-report.json` generated

### Codex Installation
- [ ] `which codex` finds binary in PATH
- [ ] `codex auth status` returns authenticated
- [ ] `~/.codex/config.toml` contains `[mcp_servers.omg-control]` section
- [ ] MCP section has `command` and `args` entries
- [ ] `/OMG:setup` detects Codex CLI
- [ ] MCP servers merged into `~/.claude/.mcp.json` (if multi-host)

### Gemini Installation
- [ ] `which gemini` finds binary in PATH
- [ ] `gemini auth status` returns authenticated
- [ ] `~/.gemini/settings.json` contains `mcpServers["omg-control"]`
- [ ] MCP entry has `command` and `args` entries

### Kimi Installation
- [ ] `which kimi` finds binary in PATH
- [ ] `~/.kimi/config.toml` contains token entry
- [ ] `~/.kimi/mcp.json` contains `mcpServers["omg-control"]`
- [ ] MCP entry has `type: "http"` and `url` entries

### Post-Install Verification
- [ ] Run `/OMG:setup` and verify setup wizard completes
- [ ] Run `/OMG:crazy <goal>` and verify execution
- [ ] Check `.omg/state/` directory for logs and state files
- [ ] Verify MCP servers respond to requests
- [ ] Test plugin features (if applicable to target)

---

## 🔍 Debugging Steps

### If Installation Fails

1. **Check environment:**
   ```bash
   echo $CLAUDE_CONFIG_DIR
   python3 --version
   which npm
   ```

2. **Check file permissions:**
   ```bash
   ls -la ~/.claude/
   ls -la ~/.codex/
   ls -la ~/.gemini/
   ls -la ~/.kimi/
   ```

3. **Validate config files:**
   ```bash
   python3 -m json.tool ~/.claude/.mcp.json
   python3 -m toml ~/.codex/config.toml  # if toml module available
   ```

4. **Check for errors in setup output:**
   ```bash
   # Re-run with verbose output
   ./OMG-setup.sh install --non-interactive 2>&1 | tee install.log
   ```

5. **Review manifest:**
   ```bash
   cat ~/.claude/.omg-manifest
   ```

6. **Check for stale files:**
   ```bash
   find ~/.claude/ -name ".omg*" -o -name "omg*" | head -20
   ```

### If Runtime Fails

1. **Check Python venv:**
   ```bash
   ~/.claude/omg-runtime/.venv/bin/python --version
   ~/.claude/omg-runtime/.venv/bin/pip list | grep fastmcp
   ```

2. **Check MCP servers:**
   ```bash
   # Test claude MCP
   python3 -m runtime.omg_mcp_server
   
   # Test codex MCP
   ~/.claude/omg-runtime/.venv/bin/python -m runtime.omg_mcp_server
   ```

3. **Check adoption report:**
   ```bash
   cat .omg/state/adoption-report.json | python3 -m json.tool
   ```

4. **Check settings application:**
   ```bash
   cat ~/.claude/settings.json | jq ._omg
   ```

---

## 📊 Installation Matrix

| Scenario | Claude | Codex | Gemini | Kimi | Notes |
|----------|--------|-------|--------|------|-------|
| Fresh install | ✅ npm | ⚠️ manual | ✅ auto-detect | ✅ auto-detect | npm hook auto-triggers |
| Update | ✅ npm | ✅ manual | ✅ auto-detect | ✅ auto-detect | Version pinning in manifest |
| Multi-host | ✅ coexist | ✅ coexist | ✅ compatible | ✅ compatible | Preset: `interop` or `labs` |
| CI/Automation | ✅ npm | ✅ manual | ⚠️ requires detection | ⚠️ requires detection | Non-interactive mode |
| Dev (symlink) | ✅ --symlink | ✅ --symlink | ✅ --symlink | ✅ --symlink | Live updates from repo |
| Uninstall | ✅ remove | ✅ remove | ✅ remove | ✅ remove | Manifest-based cleanup |

---

## 🎬 Next Actions

### Immediate (Blocking Issues)
1. Test JSON validation and recovery on malformed configs
2. Test atomic write resilience on all platforms
3. Verify TOML parser robustness (Codex-specific)
4. Test Windows compatibility for atomic writes

### High Priority
5. Test provider detection and PATH refresh requirement
6. Test plugin registry consistency (multiversion scenarios)
7. Test settings merge script presence and execution
8. Test venv Python path patching accuracy

### Medium Priority
9. Test symlink mode robustness (moved/deleted repos)
10. Test adoption report generation for mixed ecosystems
11. Document error recovery procedures
12. Create troubleshooting guide based on findings

### Low Priority
13. Performance optimization for large config files
14. Add telemetry/logging for install success rates
15. Create install wizard improvements based on UX testing

---

## 📞 Support & Contact

**Repository:** https://github.com/trac3er00/OMG  
**Issue Tracker:** https://github.com/trac3er00/OMG/issues  
**Documentation:** See CLI-ADAPTER-MAP.md and QUICK-REFERENCE.md in repository root

