<!-- GENERATED: DO NOT EDIT MANUALLY -->
# OMG Install Process Verification Index

**Purpose:** Track all CLI adapter integration points, installation flows, and critical assumptions for end-to-end verification.

**Version:** OMG 2.2.7

---

## 📖 Documentation Map

### Primary References
- **`CLI-ADAPTER-MAP.md`**
- **`QUICK-REFERENCE.md`**

### Source Files Referenced
- `runtime/mcp_config_writers.py`
- `runtime/adoption.py`
- `OMG-setup.sh`

---

<!-- OMG:GENERATED:verification-index-targets -->
## Installation Targets & Methods

### Canonical Targets
1. **Claude** — Config: `.mcp.json`
2. **Codex** — Config: `~/.codex/config.toml`
3. **Gemini** — Config: `~/.gemini/settings.json`
4. **Kimi** — Config: `~/.kimi/mcp.json`

### Compatibility Targets
5. **OpenCode** — Config: `~/.config/opencode/opencode.json`
<!-- /OMG:GENERATED:verification-index-targets -->

---

## 🔧 Verification Commands

| Name | Command |
| :--- | :--- |
| doctor | `omg doctor` |
| validate | `omg validate` |

## 📂 Cache Paths

- `.omg/cache`
