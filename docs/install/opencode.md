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
- canonical v1 contract hosts remain Claude Code and Codex
