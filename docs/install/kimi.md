# Install OMG for Kimi CLI

## Fast Path

```bash
npm install @trac3er/oh-my-god
```

If `kimi` is already on `PATH`, OMG writes an `omg-control` stdio server entry to `~/.kimi/mcp.json` during install.

## Manual Path

```bash
git clone https://github.com/trac3er00/OMG
cd OMG
./OMG-setup.sh install --mode=omg-only --preset=interop
```

Optional browser capability:

```bash
./OMG-setup.sh install --mode=omg-only --preset=interop --enable-browser
```

## Verify

- `kimi mcp list` should include `omg-control`
- `~/.kimi/mcp.json` should contain `mcpServers.omg-control`
- the configured command should point at `~/.claude/omg-runtime/.venv/bin/python`
- if browser capability is enabled, `~/.claude/omg-runtime/browser/capability.json` should exist

## Notes

- Kimi uses native MCP registration; it does not consume Claude `/OMG:*` slash commands
- OMG support on Kimi is the shared runtime plus MCP control plane

<!-- OMG:GENERATED:install-fast-path -->
## Fast Path

> **Prerequisites**: Node >=18, Python >=3.10

```bash
omg install --plan    # preview changes
omg install --apply   # apply configuration
```

This registers the OMG control plane for your host automatically.
<!-- /OMG:GENERATED:install-fast-path -->
