# Install OMG for Codex

## Fast Path

```bash
npx omg env doctor
npx omg install --plan
npx omg install --apply
```

This launcher-first path keeps mutations explicit. If you choose `npm install`, it only links the bin and still requires explicit `npx omg install --apply` for mutations.

<details><summary>Legacy clone path (advanced)</summary>

```bash
git clone https://github.com/trac3er00/OMG
cd OMG
./OMG-setup.sh install --mode=omg-only --preset=interop
```

Optional browser capability:

```bash
./OMG-setup.sh install --mode=omg-only --preset=interop --enable-browser
```

</details>

## Verify

- `codex mcp list` should include `omg-control`
- `~/.codex/config.toml` should contain `[mcp_servers.omg-control]`
- the configured command should point at `~/.claude/omg-runtime/.venv/bin/python`
- if browser capability is enabled, `~/.claude/omg-runtime/browser/capability.json` should exist

## Notes

- `/OMG:*` slash commands are Claude Code surfaces, not Codex CLI surfaces
- Codex consumes OMG through native MCP plus the generated Codex pack under `.agents/skills/omg/`
- Codex keeps its own built-in slash commands and instruction files. OMG should stay compatible with Codex's native `AGENTS.md` hierarchy and skill loading rather than trying to mirror built-in `/personality`, `/approvals`, `/agent`, or related host commands.
- Generated OMG Codex artifacts are expected to compose with the repo's `AGENTS.md` / `AGENTS.override.md` flow and the host's progressive-disclosure skill loading.

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
