# Install OMG for Gemini CLI

## Fast Path

```bash
npm install @trac3er/oh-my-god
```

If `gemini` is already on `PATH`, OMG writes an `omg-control` stdio server entry to `~/.gemini/settings.json` during install.

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

> **Prerequisite**: Node >=18

```bash
npm install -g @trac3er/oh-my-god  # put omg on PATH
omg env doctor                     # check environment
omg install --plan                 # preview changes
omg install --apply                # apply configuration
```

For project-local usage: `npm install @trac3er/oh-my-god`.
Then run commands through `npm exec omg -- <args>`.

`npm install` performs dependency resolution and bin linking.
The `postinstall` hook runs `--plan` only (no mutations).
Mutation requires explicit `omg install --apply`.
<!-- /OMG:GENERATED:install-fast-path -->
