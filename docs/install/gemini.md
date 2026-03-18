# Install OMG for Gemini CLI

## Fast Path

```bash
npx omg env doctor
npx omg install --plan
npx omg install --apply
```

This launcher-first path keeps mutations explicit. If you choose `npm install`, it only links the bin and still requires explicit `npx omg install --apply` for mutations.

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
