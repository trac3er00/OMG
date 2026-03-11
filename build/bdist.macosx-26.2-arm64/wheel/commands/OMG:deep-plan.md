---
description: "Strategic planning via the canonical plan-council bundle."
allowed-tools: Read, Grep, Glob
argument-hint: "<planning goal or feature to plan>"
---

# /OMG:deep-plan

`/OMG:deep-plan` is a compatibility path to the canonical `plan-council` bundle.

Users invoke `/OMG:deep-plan`; the runtime routes to `plan-council` for execution.
For the full behavior specification, see `plugins/advanced/commands/OMG:deep-plan.md`.

## Compatibility Notes

- This alias exists so users can invoke deep-plan workflows from the root command surface.
- Runtime behavior resolves to the `plan-council` bundle — same structured deliberation, same artifacts.
- OMG uses the `plan-council` bundle for canonical planning, dissent, and evidence workflows.
