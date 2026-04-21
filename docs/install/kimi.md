# Install OMG for Kimi CLI

<!-- OMG:GENERATED:install-fast-path -->
## Fast Path

> **Prerequisites**: macOS or Linux, Node >=18, Python >=3.10

```bash
npx omg env doctor
npx omg install --plan    # preview only, no mutations
npx omg install --apply   # apply configuration
```

The preview step is advisory only and makes no mutations until you run apply.
<!-- /OMG:GENERATED:install-fast-path -->

<details><summary>Restricted environments / manual setup</summary>

```bash
git clone https://github.com/trac3r00/OMG
cd OMG
./OMG-setup.sh install --mode=omg-only --preset=interop
```

Optional browser capability:

```bash
./OMG-setup.sh install --mode=omg-only --preset=interop --enable-browser
```

</details>

## Verify

- `kimi mcp list` should include `omg-control`
- `~/.kimi/mcp.json` should contain `mcpServers.omg-control`
- the configured command should point at `bunx omg-control`
- if browser capability is enabled, `~/.claude/omg-runtime/browser/capability.json` should exist

## Notes

- Kimi uses native MCP registration; it does not consume Claude `/OMG:*` slash commands
- OMG support on Kimi is the shared runtime plus MCP control plane
