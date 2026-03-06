---
name: omg-session-continuity
description: Use when Codex needs to preserve OMG continuity across pauses, branch changes, partial progress, or handoff preparation, especially when `.omg/state` artifacts need to stay coherent.
metadata:
  short-description: Preserve OMG handoff and session continuity in Codex
---

# OMG Session Continuity

Use this skill when stopping and resuming work matters as much as the code change itself.

## Workflow

1. Inspect `.omg/state` before changing continuity artifacts.
2. Preserve mode, handoff, and ledger context rather than rewriting them blindly.
3. Prefer additive updates over destructive replacement.
4. If the next session needs branch/readiness context, pair this with `omg-release-readiness`.

## When To Read More

- Read [references/session.md](references/session.md) when you need the minimal continuity artifacts that should survive a Codex session boundary.
