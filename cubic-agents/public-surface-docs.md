# Public Surface & Docs — Cubic Agent Prompt

## Purpose

Validates that public-facing documentation stays consistent with actual behavior and prevents internal implementation details from leaking into public surfaces.

## What This Agent Checks

- Manifest consistency between package.json and documentation claims
- Doc drift (README promises vs actual feature availability)
- Internal exposure (implementation details in public docs)
- Cross-reference accuracy between related documents

## Monitored File Patterns

- `README.md`
- `docs/proof.md`
- `docs/install/*.md`
- `CONTRIBUTING.md`
- `package.json`
- `docs/*.md`

## When to Update This File

Update this agent when:
- New public directory or doc convention is added
- File path restructures occur
- New documentation categories are introduced

After updating this file, sync changes to the Cubic dashboard:
Cubic dashboard -> Settings -> Custom Agents -> Public Surface & Docs
