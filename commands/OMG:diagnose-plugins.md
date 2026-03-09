---
description: Diagnose plugin interoperability and conflict status across OMG-supported hosts
allowed-tools: Bash(python3:*), Read, Grep, Glob
---

# /OMG:diagnose-plugins

Run `python3 scripts/omg.py diagnose-plugins --format json` and report the diagnostics result.

## Output Schema

- `schema`: `PluginDiagnosticsResult`
- `status`: `ok` | `warn` | `error`
- `records`: discovered plugin records
- `conflicts`: classified conflict entries
- `approval_states`: plugin approval states by plugin id
- `summary`: totals for records, conflicts, and severity buckets
- `next_actions`: top recommended remediations
- `elapsed_ms`: total diagnostic runtime

## Commands

```
python3 scripts/omg.py diagnose-plugins --format json
python3 scripts/omg.py diagnose-plugins --format text
python3 scripts/omg.py diagnose-plugins approve --source mcp:filesystem --host claude --reason "trusted" --format json
```

## Notes

- Base diagnostics command is read-only.
- Static mode is default; live probing must be explicit via `--live`.
- `approve` currently returns a pending stub response.
