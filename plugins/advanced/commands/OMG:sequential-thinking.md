---
description: Structured multi-step reasoning using sequential-thinking tool for complex debugging and planning.
allowed-tools: sequential-thinking_sequentialthinking, Read, Grep, Glob
argument-hint: "[problem statement to reason through]"
---

# /OMG:sequential-thinking

Use the sequential-thinking tool when the task needs explicit step-by-step reasoning,
branching, and hypothesis verification.

Execution contract:
- Start with an initial thought budget
- Revise or branch when new evidence appears
- End only when a verified conclusion is reached

Output contract:
- Return final conclusion
- Return key assumptions
- Return verification steps used
