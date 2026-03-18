# Install OMG for OpenCode

<!-- OMG:GENERATED:install-fast-path -->
## Fast Path

> **Prerequisites:** Node >= 18, Python 3.10+, macOS or Linux.

```bash
npx omg install --plan    # preview changes
npx omg install --apply   # apply configuration
```

This configures the OMG control plane for your host.
<!-- /OMG:GENERATED:install-fast-path -->

If `opencode` is on `PATH`, `npx omg install --apply` wires `omg-control` into OpenCode's MCP config using the managed OMG Python runtime.

## Manual Path

```bash
git clone https://github.com/trac3er00/OMG
cd OMG
./OMG-setup.sh install --mode=omg-only --preset=interop
```

## Verify

- OpenCode is supported as a compatibility host in v1 (not a canonical contract host)
- global config path: `~/.config/opencode/opencode.json`
- project config path: `opencode.json`
- MCP entries use the `mcp` key (not `mcpServers`)
- plugin discovery reads `.opencode/plugins/`

## Notes

- OpenCode consumes OMG through compatibility-host MCP registration
- canonical v2.2.8 behavior-parity hosts are Claude Code, Codex, Gemini CLI, and Kimi CLI
