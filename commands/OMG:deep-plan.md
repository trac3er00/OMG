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

## Deep-Plan v2 Post-Plan Flow

After plan generation completes, deep-plan enters an interactive post-plan flow:

### Classification Boundary Override (N8.4)
Before proceeding, AskUserQuestion allows user to override NEEDED/NICE/NOT-NEEDED classifications.

### Post-Plan Actions (N8.6)
User is asked to choose:
1. **Start implementing** — begins execution via `/OMG:start-work`
2. **Add more items** — re-runs deep-plan on NEW items only, merges into existing plan
3. **Validate with another model** — sends plan to Codex/Gemini if detected

### Add More Items Loop (N8.7)
When "Add more" is selected, deep-plan:
- Runs ONLY on new items (direction discovery, classification)
- Merges new items into existing phases and checklist
- Does NOT regenerate the entire plan
- Presents updated plan and returns to post-plan flow

### External Validation (N8.8)
When "Validate with another model" is selected:
- Detects available AI CLIs (Codex, Gemini, GPT)
- Sends plan to Codex for backend/security feasibility review
- Sends plan to Gemini for UX/docs clarity review
- Appends validation verdicts to plan
- Records validation evidence in plan-council.json

### Multi-Model Deep Plan (N8.9)
When multiple AI CLIs are detected at planning start:
- Claude orchestrates plan structure and direction
- Codex validates backend logic, security, and feasibility
- Gemini reviews UX implications and documentation clarity
- All feedback merged into final plan artifacts

### Multi-Model Research (N8.10)
During direction discovery, if multiple CLIs detected:
- Dispatch research questions in parallel to available CLIs
- Codex researches backend/security patterns
- Gemini researches UX/visual patterns
- Synthesize findings into plan's Domain Context and Architecture Decisions

## Compatibility Notes

- This alias exists so users can invoke deep-plan workflows from the root command surface.
- Runtime behavior resolves to the `plan-council` bundle — same structured deliberation, same artifacts.
- OMG uses the `plan-council` bundle for canonical planning, dissent, and evidence workflows.
