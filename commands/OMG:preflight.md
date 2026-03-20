---
description: "Structured OMG router that classifies risk, selects the right route, and emits an execution/evidence plan."
allowed-tools: Read, Grep, Glob, AskUserQuestion, Bash(python3:*), Bash(rg:*)
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

## Route Selection

After classifying risk, if multiple routes are viable, use `AskUserQuestion`:
- question: "Which execution route should we take?"
- header: "Route"
- options:
  - label: "[recommended route] (Recommended)", description: "[why this route fits]"
  - label: "security-check", description: "Security-sensitive or trust-bound work"
  - label: "crazy", description: "Maximum parallel multi-agent execution"
  - label: "teams", description: "Targeted single-agent dispatch"
- (api-twin and other routes available via Other)

If only one route is clearly correct, state the recommendation and proceed.
