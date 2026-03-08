# Install OMG for Claude Code

## Fast Path

```bash
npm install @trac3er/oh-my-god
```

The npm postinstall now registers the local `omg` marketplace, enables `omg@omg`, and installs the Claude plugin bundle under `~/.claude/plugins/cache/omg/omg/<version>`.

## Official Claude Plugin Flow

Claude Code's native plugin commands are still the source of truth:

```bash
claude plugin marketplace add /path/to/OMG --scope user
claude plugin install omg@omg --scope user
```

`npm install` is equivalent for OMG because the setup script now writes the marketplace registration that Claude expects.

## Run

```text
/OMG:setup
/OMG:crazy <goal>
```

## Verify

- `claude plugin list` should show `omg@omg` with `Status: enabled`
- `~/.claude/plugins/known_marketplaces.json` should contain an `omg` entry
- `~/.claude/settings.json` should contain a `statusLine` command pointing at `~/.claude/hud/omg-hud.mjs`
- `~/.claude/.mcp.json` should not duplicate the plugin-managed `filesystem` or `omg-control` servers
- `~/.claude/omg-runtime/.venv/bin/python` should exist
