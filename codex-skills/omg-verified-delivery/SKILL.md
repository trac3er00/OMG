---
name: omg-verified-delivery
description: Use when finishing OMG work in Codex and you need disciplined verification, readiness checks, reproducible evidence, or release gating before claiming completion.
metadata:
  short-description: Verify OMG delivery before completion
---

# OMG Verified Delivery

Use this skill near the end of an OMG task when Codex should prove the result instead of summarizing optimistically.

## Delivery Checklist

1. Run targeted tests first, then broader suites only if needed.
2. Run `python3 scripts/check-source-build-drift.py` when source/build mirrors are part of the change.
3. Use `python3 scripts/omg.py release readiness` when provider blockers or branch dirtiness matter.
4. Summarize evidence with exact commands and whether they passed.
5. Call out anything not verified.

## When To Read More

- Read [references/verification.md](references/verification.md) when you need the repo-standard verification sweep for OMG runtime changes.

