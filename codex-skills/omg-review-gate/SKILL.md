---
name: omg-review-gate
description: Use when Codex has already explored or implemented OMG work and now needs a Codex-only review gate covering correctness, regression risk, security-sensitive changes, and proof before handoff or completion.
metadata:
  short-description: Run a Codex-only OMG review gate
---

# OMG Review Gate

Use this skill before close-out, not at initial exploration.

## Gate

1. Review for behavioral regressions first.
2. Check security-sensitive changes explicitly.
3. Verify the claimed route still matches the work that was done.
4. Prefer findings with evidence over narrative summaries.
5. Move to `omg-verified-delivery` when the review gate is clean enough to package completion evidence.

## When To Read More

- Read [references/review.md](references/review.md) when you need the order of review checks and failure framing.
