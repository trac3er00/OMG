# Install OMG for OpenCode

## Fast Path

```bash
npm install @trac3er/oh-my-god
```

`npm install` resolves dependencies and links the `omg` binary only. The package postinstall runs `omg install --plan` as a preview, so it makes no mutations and does not write OpenCode MCP config until you later run `omg install --apply`.

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
- canonical v2.2.9 behavior-parity hosts are Claude Code, Codex, Gemini CLI, and Kimi CLI

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
