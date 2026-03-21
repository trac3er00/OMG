---
description: "Canonical validation — doctor + health-check + diagnose-plugins + contract + profile + install checks"
allowed-tools: Bash(python3:*), Bash(ls:*), Bash(cat:*), Bash(grep:*), Bash(git:*), Bash(which:*), Bash(head:*), Bash(wc:*), Bash(find:*), Read, Grep, Glob
argument-hint: "[doctor|health|plugins|all] [--format json|text] [--fix]"
---

# /OMG:validate — Unified Validation Engine

Canonical validation surface. Subsumes `/OMG:doctor`, `/OMG:health-check`, and `/OMG:diagnose-plugins`.

## Usage

```
/OMG:validate              # Run all checks (default)
/OMG:validate doctor        # Runtime/install checks only
/OMG:validate health        # Project health checks only
/OMG:validate plugins       # Plugin interop diagnostics only
/OMG:validate all           # Explicit alias for default (all checks)
```

## Sub-Commands

### `doctor` — Runtime & Install Verification

Checks Python version, fastmcp, omg-control, policy files, metadata drift, compiled bundles, host compatibility, memory, managed runtime.

```bash
python3 scripts/omg.py doctor --format json
python3 scripts/omg.py doctor --fix        # Auto-repair known issues
```

Required checks:
1. **python_version**: Python >= 3.10
2. **fastmcp**: `fastmcp` importable
3. **omg_control_reachable**: `.mcp.json` contains `omg-control`
4. **policy_files**: `commands/` or `.omg/policy.yaml` exists
5. **metadata_drift**: Version surfaces match `CANONICAL_VERSION`

Optional checks:
6. **compiled_bundles**: `dist/` contains channel bundles
7. **host_compatibility**: Host config directory exists
8. **memory_reachable**: HTTP `omg-memory` configured
9. **managed_runtime**: Managed venv exists

### `health` — Project Setup & Context Health

Checks project profile, knowledge freshness, quality gate, secrets, tools, failure patterns, context size.

1. **Profile**: `.omg/state/profile.yaml` exists with required fields
2. **Knowledge**: `.omg/knowledge/` has content, no stale files (>30 days)
3. **Quality Gate**: `.omg/state/quality-gate.json` commands are runnable
4. **Secrets**: No `.env` committed to git, no API keys in tracked files
5. **Tools**: Hooks installed, MCP servers configured
6. **Failures**: No stale failure patterns in tracker (>24h)
7. **Context Size**: Total injection <80 lines

### `plugins` — Plugin Interop Diagnostics

```bash
python3 scripts/omg.py diagnose-plugins --format json
python3 scripts/omg.py diagnose-plugins --live          # Live probing
python3 scripts/omg.py diagnose-plugins approve --source mcp:filesystem --host claude --reason "trusted"
```

Output: `PluginDiagnosticsResult { status, records, conflicts, approval_states, summary, next_actions }`

## Default Behavior (`/OMG:validate` with no argument)

Runs the full canonical validation engine:

```bash
python3 scripts/omg.py validate --format json
```

Composes:
1. **Doctor checks** — runtime/install verification
2. **Contract registry** — contract doc, schema, bundle integrity
3. **Profile governor** — governed preferences, pending confirmations
4. **Install integrity** — scripts, runtime, commands, plugins directories

## Output Schema (JSON)

```json
{
  "schema": "ValidateResult",
  "status": "pass" | "fail",
  "checks": [
    {
      "name": "check_name",
      "status": "ok" | "blocker" | "warning",
      "message": "human-readable description",
      "required": true | false
    }
  ],
  "version": "2.2.12"
}
```

## Report Format (text)

```
   PASS python_version: Python 3.12.0
   PASS fastmcp: fastmcp importable
BLOCKER omg_control_reachable: omg-control not found in .mcp.json
   PASS contract_registry: contract registry valid (0 errors)
   PASS profile_governor: profile governor ok (2 style, 1 safety) (optional)
   PASS install_integrity: install integrity ok

PASS [5] | WARN [0] | BLOCKER [1]
```

## Exit Codes

- `0` — all required checks pass
- `1` — one or more blockers detected
