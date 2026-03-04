# OAL v1.0.2

OAL (Orchestration Abstraction Layer) is a standalone orchestration layer for Claude Code.
It adds structured multi-agent workflows, intelligent model routing (Claude/Codex/Gemini), and durable session state for long-running engineering tasks.

- Version: `v1.0.2`
- Maintainer: `trac3er00`
- Repo: `git@github.com:trac3er00/OAL.git`
- Release: `https://github.com/trac3er00/OAL/releases/tag/v1.0.2`

## What OAL Solves

OAL is built for teams and solo developers who want:

- Reliable execution loops (explore -> decide -> implement -> verify)
- Strong verification discipline (no unverified completion claims)
- Better model delegation for backend, frontend, security, and architecture tasks
- Session continuity across long refactors and multi-day work

## Core Capabilities

- Multi-agent orchestration with role-specific agents
- Dynamic routing to Codex and Gemini for domain-specific tasks
- Failure tracking and escalation after repeated unsuccessful attempts
- Command surface for planning, review, security, handoff, and execution modes
- Context minimization and selective knowledge injection to reduce prompt noise

## At a Glance

- Hooks: 27 Python hooks
- Core rules: 5
- Contextual rules: 17
- Agents: 15
- Commands: 10 core + 10 advanced (+ compatibility aliases)

## Requirements

- Python `3.8+`
- Claude Code with write access to `~/.claude`

## Installation

### Standard install

```bash
chmod +x OAL-setup.sh
./OAL-setup.sh install
```

### Plugin-oriented install (recommended)

```bash
./OAL-setup.sh install --install-as-plugin
```

### Update

```bash
./OAL-setup.sh update
```

### Uninstall

```bash
./OAL-setup.sh uninstall
```

### Common flags

Supported by `OAL-setup.sh`:

- `--fresh` clean reinstall before install/update
- `--symlink` development mode with live updates from repo source
- `--install-as-plugin` install plugin bundle (plugin manifest + MCP + HUD)
- `--dry-run` preview changes without writing files
- `--non-interactive` skip prompts (CI/automation)
- `--merge-policy=ask|apply|skip` control settings merge behavior

## Plugin Update Behavior

If OAL is installed through Claude Code plugin flow (`/plugin`), update works like this:

- Claude plugin update triggers `.claude-plugin/scripts/update.sh`
- In git-backed installs, update stashes local changes (if needed) and pulls from `origin/main`
- When a git tag is available, plugin manifests are synced to the tagged version
- In cache/copy installs, update delegates to `OAL-setup.sh update`

If plugin update appears silent, check:

- `~/.claude/plugins/known_marketplaces.json` has git source for `oh-advanced-layer`
- `~/.claude/plugins/cache/oh-advanced-layer/oal/<version>/.claude-plugin/plugin.json` is valid schema
- update script exists and is executable

## Quick Start in Claude Code

After install, from your target project directory:

```text
/OAL:init
/OAL:health-check
```

Common flows:

```text
/OAL:mode implement
/OAL:escalate codex "debug auth middleware"
/OAL:crazy fix flaky tests in payment module
/OAL:handoff
```

## Command Groups

### Core commands

- `/OAL:init`
- `/OAL:project-init`
- `/OAL:domain-init`
- `/OAL:health-check`
- `/OAL:mode`
- `/OAL:escalate`
- `/OAL:teams`
- `/OAL:ccg`
- `/OAL:crazy`
- `/OAL:compat`

### Advanced commands

- `/OAL:deep-plan`
- `/OAL:learn`
- `/OAL:code-review`
- `/OAL:security-review`
- `/OAL:ship`
- `/OAL:maintainer`
- `/OAL:handoff`
- `/OAL:sequential-thinking`
- `/OAL:ralph-start`
- `/OAL:ralph-stop`

## Agent Routing Model

OAL dispatches by domain intent:

- Codex path: backend logic, debugging, algorithms, security-sensitive implementation
- Gemini path: UI/UX, layout, visual refinements, accessibility-oriented frontend work
- Claude path: orchestration, synthesis, review loops, and fallback execution

## Cognitive Modes

Set an explicit operating mode per session:

```text
/OAL:mode research
/OAL:mode architect
/OAL:mode implement
/OAL:mode clear
```

Modes are persisted to `.oal/state/mode.txt`.

## Verification and Safety

OAL enforces practical completion gates:

- Prevents unverified completion claims
- Tracks repeated failures and recommends escalation
- Validates test quality (anti-boilerplate checks)
- Preserves evidence and handoff state before context compaction

Important behavior:

- Prefer proof over assumptions
- Run checks after modifications
- Keep output tied to observable evidence

## Project State Layout

After `/OAL:init`, project state is created under `.oal/`:

```text
.oal/
  state/
    profile.yaml
    working-memory.md
    handoff.md
    ledger/
  knowledge/
  trust/
  evidence/
  shadow/
  migrations/
```

## Repository Layout (High Level)

```text
oal/
  hooks/
  rules/
    core/
    contextual/
  agents/
  commands/
  plugins/
  templates/
  runtime/
  scripts/
  OAL-setup.sh
```

## Versioning and Releases

Current version: `v1.0.2`

Recommended release flow:

```bash
git tag -a v1.0.2 -m "OAL v1.0.2"
git push origin v1.0.2
gh release create v1.0.2 --title "OAL v1.0.2" --notes "Release notes"
```

## Compatibility Notes

- OAL runs standalone (OMC not required)
- Legacy migration utilities remain available where needed
- Works alongside other plugins when command namespaces do not conflict

## Troubleshooting

### Plugin manifest invalid

If Claude reports plugin manifest schema errors:

- Keep `.claude-plugin/plugin.json` minimal and schema-compatible
- Avoid unsupported keys for your Claude Code version
- Reinstall plugin cache after manifest changes

### Plugin update does nothing

- Verify marketplace source is git-based (not local directory mode)
- Verify plugin cache points to correct version directory
- Run update script manually once to confirm output:

```bash
bash ~/.claude/plugins/cache/oh-advanced-layer/oal/*/.claude-plugin/scripts/update.sh
```

## License

MIT
