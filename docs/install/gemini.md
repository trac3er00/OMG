# Install OMG for Gemini CLI

## Fast Path

```bash
npm install -g @trac3er/oh-my-god
```

`npm install -g` resolves dependencies and links the `omg` binary on your PATH. The package postinstall runs `omg install --plan` as a preview, so it makes no mutations and does not write `~/.gemini/settings.json` until you later run `omg install --apply`.

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
omg env doctor
omg install --plan    # preview only, no mutations
omg install --apply   # apply configuration
```

The preview step is advisory only and makes no mutations until you run apply.
<!-- /OMG:GENERATED:install-fast-path -->
