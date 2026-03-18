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
- Codex keeps its own built-in slash commands and instruction files. OMG should stay compatible with Codex's native `AGENTS.md` hierarchy and skill loading rather than trying to mirror built-in `/personality`, `/approvals`, `/agent`, or related host commands.
- Generated OMG Codex artifacts are expected to compose with the repo's `AGENTS.md` / `AGENTS.override.md` flow and the host's progressive-disclosure skill loading.

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
