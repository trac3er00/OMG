# Install OMG for OpenCode

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

</details>

## Verify

- OpenCode is supported as a compatibility host in v1 (not a canonical contract host)
- global config path: `~/.config/opencode/opencode.json`
- project config path: `opencode.json`
- MCP entries use the `mcp` key (not `mcpServers`)
- plugin discovery reads `.opencode/plugins/`

## Notes

- OpenCode consumes OMG through compatibility-host MCP registration
- canonical v2.3.0 behavior-parity hosts are Claude Code, Codex, Gemini CLI, and Kimi CLI
