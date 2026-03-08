# Install OMG for Codex

## Fast Path

```bash
npm install @trac3er/oh-my-god
```

If `codex` is already on `PATH`, OMG now wires `omg-control` into `~/.codex/config.toml` during install using the managed OMG Python runtime.

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

- `codex mcp list` should include `omg-control`
- `~/.codex/config.toml` should contain `[mcp_servers.omg-control]`
- the configured command should point at `~/.claude/omg-runtime/.venv/bin/python`
- if browser capability is enabled, `~/.claude/omg-runtime/browser/capability.json` should exist

## Notes

- `/OMG:*` slash commands are Claude Code surfaces, not Codex CLI surfaces
- Codex consumes OMG through native MCP plus the generated Codex pack under `.agents/skills/omg/`
