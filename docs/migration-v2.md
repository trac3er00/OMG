# Migrating to OMG v2.0

This guide covers everything you need to know when upgrading from OMG v1.x to v2.0.

---

## Overview

OMG v2.0 introduces six new capability modules: cost tracking, git workflow automation, session analytics, test generation, dependency health monitoring, and codebase visualization. Every one of these ships **disabled by default**.

If you do nothing, your existing setup keeps working exactly as before. No commands break. No hooks change behavior. No state files get overwritten.

---

## Backward Compatibility

**All v1.x behavior is preserved when v2.0 flags are off.**

Specifically:
- All `/OMG:*` commands work unchanged
- All 27 hooks continue to fire with identical behavior
- All agents remain available with the same routing logic
- `.omg/state/` files from v1.x are untouched
- `settings.json` keys from v1.x remain valid
- The `_omg` config namespace is additive only — no keys were removed or renamed

The only change you'll notice without opting in: the version string in `settings.json` reads `2.0.0-alpha` instead of `1.0.5`.

---

## New Feature Flags

Each v2.0 feature is controlled by a flag in `_omg.features` and a corresponding environment variable. Both methods work; the env var takes precedence.

### Enabling features

**Option 1 — environment variable** (per-session, good for testing):

```bash
export OMG_COST_TRACKING_ENABLED=1
# then launch Claude Code
```

**Option 2 — settings.json** (persistent, applies to all sessions in this project):

```json
{
  "_omg": {
    "features": {
      "COST_TRACKING": true
    }
  }
}
```

### Feature reference

| Feature | Flag key | Env var | What it does |
|---------|----------|---------|--------------|
| Cost Tracking | `COST_TRACKING` | `OMG_COST_TRACKING_ENABLED=1` | Tracks token spend per session, enforces budget limits, exposes `/cost` command |
| Git Workflow | `GIT_WORKFLOW` | `OMG_GIT_WORKFLOW_ENABLED=1` | Automates branch hygiene, commit message validation, and PR readiness checks |
| Session Analytics | `SESSION_ANALYTICS` | `OMG_SESSION_ANALYTICS_ENABLED=1` | Aggregates session metrics (tool calls, error rates, duration) into `.omg/state/` |
| Test Generation | `TEST_GENERATION` | `OMG_TEST_GENERATION_ENABLED=1` | Auto-generates test stubs on Write/Edit via `test_generator_hook.py` |
| Dependency Health | `DEP_HEALTH` | `OMG_DEP_HEALTH_ENABLED=1` | Scans project dependencies for outdated packages and known vulnerabilities |
| Codebase Viz | `CODEBASE_VIZ` | `OMG_CODEBASE_VIZ_ENABLED=1` | Builds a dependency graph and renders an architecture diagram |

All flags default to `false`. You can enable any combination independently.

---

## New settings.json Keys

v2.0 adds the following keys under the `_omg` namespace. All are optional and have safe defaults.

### `_omg._version`

```json
"_version": "2.0.0-alpha"
```

Tracks the installed OMG version. Read by hooks for compatibility checks. Do not edit manually.

### `_omg.cost_budget`

Controls the budget governor behavior (used when `COST_TRACKING` is enabled).

```json
"cost_budget": {
  "session_limit_usd": 5.0,
  "thresholds": [50, 80, 95],
  "pricing": {
    "input_per_mtok": 3.0,
    "output_per_mtok": 15.0
  }
}
```

- `session_limit_usd` — hard cap per session in USD. Default: `5.0`
- `thresholds` — percentage thresholds at which warnings fire. Default: `[50, 80, 95]`
- `pricing.input_per_mtok` — cost per million input tokens. Default: `3.0`
- `pricing.output_per_mtok` — cost per million output tokens. Default: `15.0`

### `_omg.context_budget`

Controls context injection and summarization behavior.

```json
"context_budget": {
  "session_start_max_chars": 2000,
  "prompt_enhancer_max_chars": 800,
  "prompt_enhancer_max_injections": 10,
  "full_turns": 10,
  "summarize_turns": 50,
  "batch_size": 21
}
```

- `session_start_max_chars` — max characters injected at session start. Default: `2000`
- `prompt_enhancer_max_chars` — max characters per prompt enhancement injection. Default: `800`
- `prompt_enhancer_max_injections` — max injections per session. Default: `10`
- `full_turns` — turns kept in full before summarization kicks in. Default: `10`
- `summarize_turns` — turns kept after summarization. Default: `50`
- `batch_size` — batch size for context processing. Default: `21`

### `_omg.credentials`

Credential rotation reminders.

```json
"credentials": {
  "rotation_schedule_days": 90,
  "expiry_warning_days": 14
}
```

### `_omg.features` (new keys)

The six new feature flags added in v2.0:

```json
"features": {
  "COST_TRACKING": false,
  "GIT_WORKFLOW": false,
  "SESSION_ANALYTICS": false,
  "TEST_GENERATION": false,
  "DEP_HEALTH": false,
  "CODEBASE_VIZ": false,
  "CONTEXT_MANAGER": false
}
```

`CONTEXT_MANAGER` is an internal flag for the context budget system. Leave it at `false` unless directed otherwise.

---

## New .omg/state/ Files

When v2.0 features are active, they write to new state files under `.omg/state/`. These files are created on first use — they won't appear until you run the relevant command or trigger the relevant hook.

### `.omg/state/cost-ledger.jsonl`

Created by: `COST_TRACKING` feature  
Format: newline-delimited JSON

Tracks token usage and estimated cost per tool call. Each line is one event:

```json
{"ts": "2026-03-04T10:00:00Z", "tool": "Bash", "input_tok": 1200, "output_tok": 340, "cost_usd": 0.0087}
```

This file grows over time. It's safe to delete — the next session starts a fresh ledger.

### `.omg/state/tool-ledger.jsonl`

Created by: `tool-ledger.py` hook (active in v1.x, extended in v2.0)  
Format: newline-delimited JSON

Records every Write/Edit/MultiEdit tool call with file path, timestamp, and session ID. v2.0 extends the schema with additional metadata fields when `SESSION_ANALYTICS` is enabled.

### `.omg/state/dependency-graph.json`

Created by: `CODEBASE_VIZ` feature, via `/deps` or `/arch` commands  
Format: JSON

Stores the parsed dependency graph for the project. Structure:

```json
{
  "generated_at": "2026-03-04T10:00:00Z",
  "nodes": [...],
  "edges": [...]
}
```

Regenerated on each `/deps` or `/arch` run. Safe to delete.

### `.omg/state/arch-diagram.png`

Created by: `CODEBASE_VIZ` feature, via `/arch` command  
Format: PNG image (optional)

Rendered architecture diagram from the dependency graph. Only created if a rendering backend is available. If the file is missing, `/arch` falls back to text output.

---

## New Commands

v2.0 adds four commands, each gated by its corresponding feature flag.

### `/cost`

Requires: `COST_TRACKING`

Shows current session spend, remaining budget, and a breakdown by tool type. Reads from `.omg/state/cost-ledger.jsonl`.

```text
/cost
```

### `/stats`

Requires: `SESSION_ANALYTICS`

Displays session metrics: total tool calls, error rate, most-used tools, and session duration.

```text
/stats
```

### `/deps`

Requires: `DEP_HEALTH`

Scans project dependencies and reports outdated packages, known vulnerabilities, and health score. Also writes `.omg/state/dependency-graph.json`.

```text
/deps
```

### `/arch`

Requires: `CODEBASE_VIZ`

Generates and displays the architecture diagram. Writes `.omg/state/dependency-graph.json` and optionally `.omg/state/arch-diagram.png`.

```text
/arch
```

---

## Troubleshooting

### Feature not working after enabling

Check that the flag is set correctly. Both methods should work:

```bash
# env var method
echo $OMG_COST_TRACKING_ENABLED   # should print 1

# settings.json method — verify the key exists and is true
cat settings.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['_omg']['features']['COST_TRACKING'])"
```

If using `settings.json`, make sure you're editing the project-level file (in your project root), not a user-level file.

### Hook errors on startup

All v2.0 hooks exit with code `0` even on failure — they never block Claude Code from starting. Diagnostic output goes to stderr. To see it:

```bash
python3 ~/.claude/hooks/budget_governor.py 2>&1
```

If a hook is crashing silently, check:
- Python 3.8+ is available at `python3`
- The hook file exists at `~/.claude/hooks/`
- Required state directories exist (`.omg/state/`)

### Missing state files

State files are created on first use. If `.omg/state/cost-ledger.jsonl` doesn't exist, run `/cost` once to initialize it. Same for other state files:

| Missing file | Run this |
|---|---|
| `cost-ledger.jsonl` | `/cost` |
| `dependency-graph.json` | `/deps` |
| `arch-diagram.png` | `/arch` |
| `tool-ledger.jsonl` | Make any Write/Edit call |

### "Command not found" for /cost, /stats, /deps, /arch

These commands require their feature flags to be enabled. Check `settings.json` or set the env var before launching Claude Code.

### Settings merge conflicts after update

If `OMG-setup.sh update` reports merge conflicts in `settings.json`, use `--merge-policy=ask` to review each conflict:

```bash
./OMG-setup.sh update --merge-policy=ask
```

The `_omg` block is additive — your existing values won't be overwritten unless you explicitly accept the merge.

---

## Rollback

To disable all v2.0 features and return to v1.x behavior:

**Option 1 — set all flags to false in settings.json:**

```json
{
  "_omg": {
    "features": {
      "COST_TRACKING": false,
      "GIT_WORKFLOW": false,
      "SESSION_ANALYTICS": false,
      "TEST_GENERATION": false,
      "DEP_HEALTH": false,
      "CODEBASE_VIZ": false,
      "CONTEXT_MANAGER": false
    }
  }
}
```

This is the default state — if you haven't changed these, you're already in v1.x mode.

**Option 2 — unset env vars:**

```bash
unset OMG_COST_TRACKING_ENABLED
unset OMG_GIT_WORKFLOW_ENABLED
unset OMG_SESSION_ANALYTICS_ENABLED
unset OMG_TEST_GENERATION_ENABLED
unset OMG_DEP_HEALTH_ENABLED
unset OMG_CODEBASE_VIZ_ENABLED
```

**Option 3 — full downgrade:**

If you need to pin to v1.0.5 exactly:

```bash
npm install @trac3er/oh-my-god@1.0.5
./OMG-setup.sh install --fresh
```

This reinstalls the v1.0.5 hooks, rules, and agents. Your `.omg/state/` files are preserved.
