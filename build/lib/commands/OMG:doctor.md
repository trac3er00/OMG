---
description: Canonical install and runtime verification for OMG
allowed-tools: Bash(python3:*), Read, Grep, Glob
---

# /OMG:doctor

Run `python3 scripts/omg.py doctor --format json` and report results.

## Required Checks

1. **python_version**: Python >= 3.10 installed and active.
2. **fastmcp**: `fastmcp` package importable (needed for MCP server).
3. **omg_control_reachable**: `.mcp.json` contains `omg-control` with stdio transport.
4. **policy_files**: `commands/` directory or `.omg/policy.yaml` exists.
5. **metadata_drift**: All public version surfaces match `CANONICAL_VERSION`.

## Optional Checks

6. **compiled_bundles**: `dist/` contains compiled channel bundles.
7. **host_compatibility**: Host config directory (e.g. `~/.claude`) exists.
8. **memory_reachable**: HTTP `omg-memory` configured (never required).
9. **managed_runtime**: Managed venv at `$CLAUDE_DIR/omg-runtime/.venv` exists.

## Output

Each check reports `name`, `status` (`ok` | `blocker` | `warning`), and `message`.

Exit code 0 when all **required** checks pass. Non-zero otherwise.

```
python3 scripts/omg.py doctor --format json
```

## Legacy Compat

`omg compat run --skill omg-doctor` routes to the same engine.
