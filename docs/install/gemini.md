# Install OMG for Gemini CLI

<!-- OMG:GENERATED:install-fast-path -->
## Fast Path

> **Prerequisites:** Node >= 18, Python 3.10+, macOS or Linux.

```bash
npx omg install --plan    # preview changes
npx omg install --apply   # apply configuration
```

This configures the OMG control plane for your host.
<!-- /OMG:GENERATED:install-fast-path -->

If `gemini` is on `PATH`, `npx omg install --apply` writes the `omg-control` stdio server entry to `~/.gemini/settings.json`.

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

- `gemini mcp list` should include `omg-control`
- `~/.gemini/settings.json` should contain `mcpServers.omg-control`
- the configured command should point at `~/.claude/omg-runtime/.venv/bin/python`
- if browser capability is enabled, `~/.claude/omg-runtime/browser/capability.json` should exist

## Notes

- Gemini uses native MCP registration; it does not consume Claude `/OMG:*` slash commands
- OMG support on Gemini is the shared runtime plus MCP control plane
