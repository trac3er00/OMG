# Install OMG for Kimi CLI

## Fast Path

```bash
npm install @trac3er/oh-my-god
```

`npm install` resolves dependencies and links the `omg` binary only. The package postinstall runs `omg install --plan` as a preview, so it makes no mutations and does not write `~/.kimi/mcp.json` until you later run `omg install --apply`.

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
omg env doctor
omg install --plan    # preview only, no mutations
omg install --apply   # apply configuration
```

The preview step is advisory only and makes no mutations until you run apply.
<!-- /OMG:GENERATED:install-fast-path -->
