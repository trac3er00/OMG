# OMG v1.0.5

OMG (Oh My God) is a standalone orchestration layer for Claude Code.
It adds structured multi-agent workflows, intelligent model routing (Claude/Codex/Gemini/Kimi), and durable session state for long-running engineering tasks.

- Version: `v1.0.5`
- npm: `npm install @trac3er/oh-my-god`
- Maintainer: `trac3er00`
- Repo: `git@github.com:trac3er00/OMG.git`
- Release: `https://github.com/trac3er00/OMG/releases/tag/v1.0.5`

## What OMG Solves

OMG is built for teams and solo developers who want:

- Reliable execution loops (explore -> decide -> implement -> verify)
- Strong verification discipline (no unverified completion claims)
- Better model delegation for backend, frontend, security, and architecture tasks
- Session continuity across long refactors and multi-day work

## Core Capabilities

- Multi-agent orchestration with role-specific agents
- Dynamic routing to Codex, Gemini, and Kimi for domain-specific tasks
- Failure tracking and escalation after repeated unsuccessful attempts
- Command surface for planning, review, security, handoff, and execution modes
- Context minimization and selective knowledge injection to reduce prompt noise

## At a Glance

- Hooks: 27 Python hooks
- Core rules: 5
- Contextual rules: 17
- Agents: 21
- Commands: 18 (`/OMG:*` namespace)

## Requirements

- Python `3.8+`
- Claude Code with write access to `~/.claude`

## Installation

### Via npm (recommended)

```bash
npm install @trac3er/oh-my-god
```

Or install the latest version explicitly:

```bash
npm install @trac3er/oh-my-god@latest
```

### Via git

```bash
git clone git@github.com:trac3er00/OMG.git
cd OMG
chmod +x OMG-setup.sh
./OMG-setup.sh install
```

### Plugin-oriented install

```bash
./OMG-setup.sh install --install-as-plugin
```

### Update

```bash
./OMG-setup.sh update
```

### Uninstall

```bash
./OMG-setup.sh uninstall
```

### Common flags

Supported by `OMG-setup.sh`:

- `--fresh` clean reinstall before install/update
- `--symlink` development mode with live updates from repo source
- `--install-as-plugin` install plugin bundle (plugin manifest + MCP + HUD)
- `--dry-run` preview changes without writing files
- `--non-interactive` skip prompts (CI/automation)
- `--merge-policy=ask|apply|skip` control settings merge behavior

## Plugin Update Behavior

If OMG is installed through Claude Code plugin flow (`/plugin`), update works like this:

- Claude plugin update triggers `.claude-plugin/scripts/update.sh`
- In git-backed installs, update stashes local changes (if needed) and pulls from `origin/main`
- When a git tag is available, plugin manifests are synced to the tagged version
- In cache/copy installs, update delegates to `OMG-setup.sh update`

If plugin update appears silent, check:

- `~/.claude/plugins/known_marketplaces.json` has git source for `oh-advanced-layer`
- `~/.claude/plugins/cache/oh-advanced-layer/oal/<version>/.claude-plugin/plugin.json` is valid schema
- update script exists and is executable

## Quick Start in Claude Code

After install, from your target project directory:

```text
/OMG:init
/OMG:health-check
```

Common flows:

```text
/OMG:mode implement
/OMG:escalate codex "debug auth middleware"
/OMG:crazy fix flaky tests in payment module
/OMG:handoff
```

## Command Groups

### Core commands

- `/OMG:init`
- `/OMG:project-init`
- `/OMG:domain-init`
- `/OMG:health-check`
- `/OMG:mode`
- `/OMG:escalate`
- `/OMG:teams`
- `/OMG:ccg`
- `/OMG:crazy`
- `/OMG:compat`

### Advanced commands

- `/OMG:deep-plan`
- `/OMG:learn`
- `/OMG:code-review`
- `/OMG:security-review`
- `/OMG:ship`
- `/OMG:maintainer`
- `/OMG:handoff`
- `/OMG:sequential-thinking`
- `/OMG:ralph-start`
- `/OMG:ralph-stop`
- `/OMG:theme`

## Agent Routing Model

OMG dispatches by domain intent:

- Codex path: backend logic, debugging, algorithms, security-sensitive implementation
- Gemini path: UI/UX, layout, visual refinements, accessibility-oriented frontend work
- Kimi path: long-context inspection, synthesis, workspace analysis, and local runtime triage
- Claude path: orchestration, synthesis, review loops, and fallback execution

## Cognitive Modes

Set an explicit operating mode per session:

```text
/OMG:mode research
/OMG:mode architect
/OMG:mode implement
/OMG:mode clear
```

Modes are persisted to `.omg/state/mode.txt`.

## Verification and Safety

OMG enforces practical completion gates:

- Prevents unverified completion claims
- Tracks repeated failures and recommends escalation
- Validates test quality (anti-boilerplate checks)
- Preserves evidence and handoff state before context compaction

Important behavior:

- Prefer proof over assumptions
- Run checks after modifications
- Keep output tied to observable evidence

## Project State Layout

After `/OMG:init`, project state is created under `.omg/`:

```text
.omg/
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
omg/
  hooks/
  rules/
    core/
    contextual/
  agents/
  commands/
  codex-skills/
  templates/
  runtime/
  scripts/
  OMG-setup.sh
```

## Versioning and Releases

Current version: `v1.0.5`

### v1.0.5 release notes

- npm `install` now auto-registers OMG as a Claude Code plugin via `postinstall` hook with npm context detection.
- Added `.mcp.json` and `hud/` to the npm package (previously excluded by `.npmignore`).
- `.claude-plugin/scripts/install.sh` now passes `--install-as-plugin --non-interactive` flags.
- Added `OMG-setup.sh` fallback MCP config heredoc for npm installs missing `.mcp.json`.
- New `runtime/tmux_session_manager.py` provides persistent tmux sessions for Codex/Gemini invocations with sentinel-based completion detection.
- `runtime/team_router.py` now routes Codex/Gemini calls through persistent tmux sessions when available, with graceful subprocess fallback.
- Added 20 new tests across 4 test files covering plugin auto-registration and tmux integration (1580 total tests passing).

### v1.0.4 emergency installation bug fix notes

- Fixed npm global install failures in non-TTY environments by auto-enabling non-interactive merge behavior in `OMG-setup.sh`.
- Removed a fragile dry-run merge preview pipeline that could terminate early under `set -euo pipefail`.
- Updated npm packaging to include required install-time assets (`settings.json` template and `lab/`).
- Added regression coverage for non-TTY install merge flow in `tests/e2e/test_setup_script.py`.

### v1.0.3 emergency installation bug fix notes

- Fixed npm global install failures in non-TTY environments by auto-enabling non-interactive merge behavior in `OMG-setup.sh`.
- Removed a fragile dry-run merge preview pipeline that could terminate early under `set -euo pipefail`.
- Updated npm packaging to include required install-time assets (`settings.json` template and `lab/`).
- Added regression coverage for non-TTY install merge flow in `tests/e2e/test_setup_script.py`.

Releases are automated via GitHub Actions. When a version tag is pushed, the `publish-npm.yml` workflow automatically publishes to npm:

```bash
# bump version in package.json, then:
git tag v1.0.5
git push origin v1.0.5
# → GitHub Actions auto-publishes @trac3er/oh-my-god@1.0.5 to npm
```

Manual release (if needed):

```bash
gh release create v1.0.5 --title "OMG v1.0.5" --notes "Release notes"
```

### Runtime Readiness Gates

OMG runtime verification is split into two GitHub Actions workflows:

- `.github/workflows/omg-runtime-readiness.yml`
  - source/build drift gate
  - runtime/provider suites
  - hooks/security/performance suites
  - compat/HUD/theme/ecosystem suites
  - full `python3 -m pytest -q`
- `.github/workflows/omg-nightly-provider-smoke.yml`
  - `omg providers status --smoke --host-mode claude_dispatch`
  - `omg providers smoke --provider all --host-mode claude_dispatch`
  - artifact upload for nightly/provider evidence

Use these workflows as the repository-level runtime gate before release tagging or broader provider rollout.

Provider readiness is reported through a shared contract used by `omg providers status`, setup output, and nightly evidence:

- `local_steps`: local bootstrap work still required, such as `bootstrap_host_config` or `remove_incompatible_feature_flags`
- `provider_steps`: provider-side remediation such as `login_to_provider` or `appeal_provider_account`
- `native_ready_reasons`: machine-readable reasons that block provider-native OMG
- `dispatch_ready_reasons`: machine-readable reasons that block `claude_dispatch`

Operator commands:

- `omg providers repair --provider codex` backs up `~/.codex/config.toml` and removes incompatible feature flags such as `rmcp_client`
- `omg release readiness` summarizes branch dirtiness, provider blockers, and release gating reasons

This is the expected interpretation of current provider truth on `2026-03-06`:

- `kimi` may reach `native_ready=true` after local configuration is complete
- `codex` is commonly blocked by `provider_login_required` plus incompatible feature flags until repaired
- `gemini` may be blocked by `provider_service_disabled` depending on account state

## Compatibility Notes

- OMG runs fully standalone
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

## New in v1.1 (Enhancement Release)

### Feature Flags

All new features are disabled by default. Enable via environment variables or `settings.json`:

| Feature | Env Var | Default |
|---------|---------|---------|
| IntentGate keyword detection | `OMG_INTENTGATE_ENABLED=1` | Off |
| Multi-credential store | `OMG_MULTI_CREDENTIAL_ENABLED=1` | Off |
| Model roles routing | `OMG_MODEL_ROLES_ENABLED=1` | Off |
| LSP client | `OMG_LSP_ENABLED=1` | Off |
| Hashline anchors | `OMG_HASHLINE_ENABLED=1` | Off |
| Python REPL | `OMG_PYTHON_REPL_ENABLED=1` | Off |
| Web search | `OMG_WEB_SEARCH_ENABLED=1` | Off |
| Browser automation | `OMG_BROWSER_ENABLED=1` | Off |
| SSH manager | `OMG_SSH_ENABLED=1` | Off |
| Themes | `OMG_THEMES_ENABLED=true` | Off |
| Rust engine | `OMG_RUST_ENGINE_ENABLED=1` | Off |

You can also enable features in `settings.json` under `_omg.features`:

```json
{
  "_omg": {
    "features": {
      "THEMES": true,
      "INTENTGATE": true
    }
  }
}
```

### New Commands

- `/OMG:theme` — Interactive theme selector with `--list`, `--preview`, `--set`, and `--auto` modes

### New Agents

v1.1 ships with expanded agent coverage:

- `omg-api-builder` — API scaffolding and endpoint design
- `omg-architect` — System design and architecture decisions
- `omg-backend-engineer` — Backend implementation tasks
- `omg-critic` — Code review and critique
- `omg-database-engineer` — Schema design and query optimization
- `omg-escalation-router` — Intelligent escalation to Codex/Gemini/Kimi
- `omg-frontend-designer` — UI/UX implementation
- `omg-infra-engineer` — Infrastructure and DevOps tasks
- `omg-qa-tester` — Test writing and quality assurance
- `omg-security-auditor` — Security review and vulnerability analysis
- `omg-testing-engineer` — Test strategy and coverage

## Migration Guide

### Upgrading from OMG v1.0 to v1.1

All new features default to `False` and are fully backward-compatible. Existing workflows continue unchanged.

To adopt new features selectively:

1. **Enable via env var** before launching Claude Code:
   ```bash
   export OMG_THEMES_ENABLED=true
   export OMG_MODEL_ROLES_ENABLED=1
   ```

2. **Or enable in `settings.json`** for persistent config:
   ```json
   {
     "_omg": {
       "features": {
         "THEMES": true,
         "MODEL_ROLES": true
       }
     }
   }
   ```

3. **No breaking changes** — all v1.0 commands, agents, and hooks remain intact.

4. **New command**: `/OMG:theme` is available immediately after update, gated by `OMG_THEMES_ENABLED`.
