# Install OMG for Claude Code

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

## Official Claude Plugin Flow

Claude Code's native plugin commands are still the source of truth:

```bash
claude plugin marketplace add /path/to/OMG --scope user
claude plugin install omg@omg --scope user
```

Run `npx omg install --apply` after reviewing the preview if you want OMG to write Claude-facing configuration.

Claude-specific note:

- Claude's newer host model treats custom task surfaces as skills first. Legacy `.claude/commands/` entries may still work, but OMG should be installed and verified through the plugin-managed marketplace/skill surface, not by checking for standalone command markdown files.
- OMG does not try to shadow Claude's built-in slash commands; it stays on its own `/OMG:*` namespace and native plugin/skill surfaces.

Optional browser capability:

<details><summary>Optional: browser via legacy setup script</summary>

```bash
./OMG-setup.sh install --enable-browser
```

</details>

That enables OMG's browser capability metadata for `/OMG:browser` and records the preferred upstream Playwright CLI command under `~/.claude/omg-runtime/browser/capability.json`.

## Verify

- `claude plugin list` should show `omg@omg` with `Status: enabled`
- `~/.claude/plugins/known_marketplaces.json` should contain an `omg` entry
- the installed plugin cache should contain `.claude-plugin/plugin.json` for the current OMG version
- `~/.claude/settings.json` should contain a `statusLine` command pointing at `~/.claude/hud/omg-hud.mjs`
- `~/.claude/.mcp.json` should not duplicate the plugin-managed `omg-control` server
- `~/.claude/omg-runtime/.venv/bin/python` should exist
- if browser capability is enabled, `~/.claude/omg-runtime/browser/capability.json` should exist
