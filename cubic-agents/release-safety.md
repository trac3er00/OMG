# Release Safety — Cubic Agent Prompt

## Purpose

Guards the release pipeline by ensuring workflow integrity, proper secret handling, and preservation of release gates that prevent broken versions from shipping.

## What This Agent Checks

- Workflow integrity (no unauthorized modifications to release workflows)
- Secret handling (secrets referenced correctly, no hardcoded values)
- Release gate preservation (readiness checks not bypassed or weakened)
- Version bump correctness in automated release steps

## Monitored File Patterns

- `.github/workflows/*.yml`
- `scripts/*.py`
- `scripts/*.sh`
- `package.json`
- `RELEASING.md`

## When to Update This File

Update this agent when:
- New workflow or release step is added
- Release gate logic changes
- New scripts are added to the release pipeline

After updating this file, sync changes to the Cubic dashboard:
Cubic dashboard -> Settings -> Custom Agents -> Release Safety
