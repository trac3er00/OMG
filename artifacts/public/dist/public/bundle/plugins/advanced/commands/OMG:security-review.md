---
description: Deprecated alias to OMG's canonical security-check pipeline.
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(rg:*)
argument-hint: "[path or '.' for the current project]"
---

# /OMG:security-review — Deprecated Alias

`/OMG:security-review` remains available only for compatibility.

Use `/OMG:security-check` instead. The canonical pipeline now owns:

- normalized security findings
- dependency and AST enrichment
- evidence-ready provenance and trust scores
- reuse across CLI, compat routing, control plane, MCP, and ship flows
