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

## Verify

- `gemini mcp list` should include `omg-control`
- `~/.gemini/settings.json` should contain `mcpServers.omg-control`
- the configured command should point at `~/.claude/omg-runtime/.venv/bin/python`

## Notes

- Gemini uses native MCP registration; it does not consume Claude `/OMG:*` slash commands
- OMG support on Gemini is the shared runtime plus MCP control plane
