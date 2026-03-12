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

Claude-specific note:

- Claude's newer host model treats custom task surfaces as skills first. Legacy `.claude/commands/` entries may still work, but OMG should be installed and verified through the plugin-managed marketplace/skill surface, not by checking for standalone command markdown files.
- OMG does not try to shadow Claude's built-in slash commands; it stays on its own `/OMG:*` namespace and native plugin/skill surfaces.

Optional browser capability:

```bash
./OMG-setup.sh install --enable-browser
```

That enables OMG's browser capability metadata for `/OMG:browser` and records the preferred upstream Playwright CLI command under `~/.claude/omg-runtime/browser/capability.json`.

## Run

```text
/OMG:setup
/OMG:crazy <goal>
```

## Verify

- `claude plugin list` should show `omg@omg` with `Status: enabled`
- `~/.claude/plugins/known_marketplaces.json` should contain an `omg` entry
- the installed plugin cache should contain `.claude-plugin/plugin.json` for the current OMG version
- `~/.claude/settings.json` should contain a `statusLine` command pointing at `~/.claude/hud/omg-hud.mjs`
- `~/.claude/.mcp.json` should not duplicate the plugin-managed `omg-control` server
- `~/.claude/omg-runtime/.venv/bin/python` should exist
- if browser capability is enabled, `~/.claude/omg-runtime/browser/capability.json` should exist
