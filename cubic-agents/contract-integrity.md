# Contract Integrity — Cubic Agent Prompt

## Purpose

Ensures version parity across all surfaces and validates that contract schemas remain complete and synchronized with runtime implementations.

## What This Agent Checks

- Snapshot drift between generated artifacts and source definitions
- Version parity across package.json, plugin metadata, and release tags
- Contract schema completeness (no missing required fields)
- Schema changes that could break backward compatibility

## Monitored File Patterns

- `package.json`
- `runtime/*.py`
- `contracts/*.json`
- `schemas/*.json`
- `.claude/`, `.cursor/`, `.windsurf/` (host config directories)
- `dist/**/*`

## When to Update This File

Update this agent when:
- New contract fields or schema changes are added
- File path restructures occur (e.g., `runtime/` renamed)
- New host directories are added that contain versioned metadata

After updating this file, sync changes to the Cubic dashboard:
Cubic dashboard -> Settings -> Custom Agents -> Contract Integrity
