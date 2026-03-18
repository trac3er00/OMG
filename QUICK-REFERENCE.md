<!-- GENERATED: DO NOT EDIT MANUALLY -->
# OMG CLI Adapter Quick Reference

## 🎯 Core Integration Points

### Canonical Hosts

| Host | Config File |
| :--- | :--- |
| claude | `.mcp.json` |
| codex | `~/.codex/config.toml` |
| gemini | `~/.gemini/settings.json` |
| kimi | `~/.kimi/mcp.json` |

### Release Channels

- `public`
- `enterprise`

### Preset Quick Reference

| Preset | Key Features |
| :--- | :--- |
| safe | None |
| balanced | SETUP, SETUP_WIZARD, MEMORY_AUTOSTART, SESSION_ANALYTICS, CONTEXT_MANAGER... |
| interop | SETUP, SETUP_WIZARD, MEMORY_AUTOSTART, SESSION_ANALYTICS, CONTEXT_MANAGER... |
| labs | SETUP, SETUP_WIZARD, MEMORY_AUTOSTART, SESSION_ANALYTICS, CONTEXT_MANAGER... |
| buffet | SETUP, SETUP_WIZARD, MEMORY_AUTOSTART, SESSION_ANALYTICS, CONTEXT_MANAGER... |
| production | SETUP, SETUP_WIZARD, MEMORY_AUTOSTART, SESSION_ANALYTICS, CONTEXT_MANAGER... |

### Quick Commands

| Task | Command |
| :--- | :--- |
| Install (preview) | `npx omg install --plan` |
| Install (apply) | `npx omg install --apply` |
| Diagnostics | `npx omg doctor` |
| Environment check | `npx omg env doctor` |
| Ship | `npx omg ship` |
| Proof dashboard | `npx omg proof open --html` |
| Explain run | `npx omg explain run <id>` |
| Blocked inspection | `npx omg blocked --last` |
| Validate | `npx omg validate` |
| Contract validate | `npx omg contract validate` |
