---
name: omg-release-readiness
description: Use when Codex needs to decide whether OMG work is actually ready to land, especially when branch dirtiness, provider blockers, or release-readiness evidence should be checked before pushing or opening a PR.
metadata:
  short-description: Check OMG release readiness from Codex
---

# OMG Release Readiness

Use this skill near the integration boundary.

## Workflow

1. Run `python3 scripts/omg.py release readiness`.
2. Inspect blocked providers, local steps, and provider steps before pushing.
3. Treat release blockers as first-class evidence, not optional warnings.
4. Keep the final summary tied to exact readiness output.

## When To Read More

- Read [references/release.md](references/release.md) when you need the exact release-readiness interpretation.
