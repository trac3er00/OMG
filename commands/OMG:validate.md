---
description: Canonical validation — doctor + contract + profile + install checks
allowed-tools: Bash(python3:*), Bash(ls:*), Bash(cat:*), Bash(grep:*), Bash(git:*), Read, Grep, Glob
---

# /OMG:validate

Run the canonical OMG validation engine that composes all verification surfaces:

1. **Doctor checks**: Python version, fastmcp, omg-control, policy files, metadata drift, compiled bundles, host compatibility, memory, managed runtime
2. **Contract registry**: Validates contract doc, schema, and bundle integrity
3. **Profile governor**: Verifies governed preferences structure and pending confirmations
4. **Install integrity**: Confirms scripts, runtime, commands, and plugins directories exist

## Usage

```bash
# Human-readable output (default)
python3 scripts/omg.py validate

# Machine-readable JSON
python3 scripts/omg.py validate --format json
```

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
  "version": "2.7.0"
}
```

## Exit Codes

- `0` — all required checks pass
- `1` — one or more blockers detected

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
