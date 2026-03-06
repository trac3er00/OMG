---
name: omg-runtime-triage
description: Use when Codex needs to inspect OMG runtime behavior, provider smoke results, long-context traces, or local workspace evidence before deciding whether Codex, Gemini, or Kimi should handle the next step.
metadata:
  short-description: Triage runtime and provider evidence in Codex
---

# OMG Runtime Triage

Use this skill when the work is mostly diagnosis.

## Workflow

1. Gather local evidence first:
   - `python3 scripts/omg.py providers status --smoke`
   - `python3 scripts/omg.py providers smoke --provider all --host-mode claude_dispatch`
2. Keep `kimi` scoped to long-context synthesis, workspace inspection, and local runtime triage.
3. Use Codex to interpret the evidence and decide whether to continue with Codex, escalate to Gemini, or synthesize with Kimi.
4. Prefer explicit fallback reasons over vague summaries.

## When To Read More

- Read [references/triage.md](references/triage.md) when you need the expected provider/readiness signals.
