# Install OMG for OpenCode

## Fast Path

```bash
npm install @trac3er/oh-my-god
```

If `opencode` is already on `PATH`, OMG wires `omg-control` into OpenCode's MCP config during install using the managed OMG Python runtime.

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
- canonical v2.2.5 behavior-parity hosts are Claude Code, Codex, Gemini CLI, and Kimi CLI

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
