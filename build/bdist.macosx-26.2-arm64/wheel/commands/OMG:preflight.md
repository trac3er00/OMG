---
description: "Structured OMG router that classifies risk, selects the right route, and emits an execution/evidence plan."
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(rg:*)
argument-hint: "\"<goal>\""
---

# /OMG:preflight — Structured Router

Use `preflight` when the goal is clear but the safest execution route is not.

## Output Contract

- restated goal
- task class
- risk class
- recommended route
- required tools and MCPs
- missing constraints
- evidence requirements

## Typical Routes

- `security-check` for security-sensitive or trust-bound work
- `api-twin` for contract replay and offline integration work
- `crazy` for parallel execution
- `teams` for targeted agent dispatch
