---
description: "Strategic planning via the canonical plan-council bundle with classification and multi-model validation."
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "<planning goal or feature to plan>"
---

# /OMG:deep-plan

`/OMG:deep-plan` is a compatibility path to the canonical `plan-council` bundle.

Users invoke `/OMG:deep-plan`; the runtime routes to `plan-council` for execution.
For the full behavior specification, see `plugins/advanced/commands/OMG:deep-plan.md`.

## Deep-Plan v2 Workflow

### Item Classification

Every plan item is classified as:
- **NEEDED** — Required for the stated goal
- **NICE-TO-HAVE** — Valuable but not blocking
- **NOT-NEEDED** — Out of scope or premature

Classification includes rationale. User can override at boundaries via AskUserQuestion.

### Plan Structure

Plans are stored in `.omg/plans/<plan-id>/`:
```
.omg/plans/<plan-id>/
  plan.md          # Human-readable plan
  checklist.md     # Execution checklist
  plan.json        # Machine-readable plan
```

Each feature/category gets a suggested PR-ready branch name.

### File-Overlap Analysis

Plans analyze which branches touch overlapping files and flag merge conflict risk.

### Post-Plan Actions

After plan generation, the user is asked:
1. **Start implementing** — begins execution via `/OMG:ralph start`
2. **Add more** — re-runs deep-plan on NEW items only, merges into existing plan
3. **Validate with another model** — sends plan to Codex/Gemini if detected

### Multi-Model Planning

When multiple AI CLIs are detected (Codex, Gemini, etc.):
- Claude orchestrates plan structure
- Codex validates for gaps and edge cases
- Gemini reviews UX/visual implications

## Compatibility Notes

- This alias exists so users can invoke deep-plan workflows from the root command surface.
- Runtime behavior resolves to the `plan-council` bundle — same structured deliberation, same artifacts.
- OMG uses the `plan-council` bundle for canonical planning, dissent, and evidence workflows.
