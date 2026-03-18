<!-- GENERATED: DO NOT EDIT MANUALLY -->
# OMG CLI Adapter Quick Reference

## 🎯 Core Integration Points

<!-- OMG:GENERATED:quick-reference-hosts -->
### Canonical Hosts

| Host | Config File |
| :--- | :--- |
| claude | `.mcp.json` |
| codex | `~/.codex/config.toml` |
| gemini | `~/.gemini/settings.json` |
| kimi | `~/.kimi/mcp.json` |

### Compatibility Hosts

| Host | Config File |
| :--- | :--- |
| opencode | `~/.config/opencode/opencode.json` |
<!-- /OMG:GENERATED:quick-reference-hosts -->

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
| Install | `omg install --plan` |
| Diagnostics | `omg doctor` |
| Ship | `omg ship` |
| Sign policy pack | `omg policy-pack sign <pack_id> --key-path <key>` |
| Verify policy packs | `omg policy-pack verify --all` |
| Generate signing key | `omg policy-pack keygen --output <path>` |
