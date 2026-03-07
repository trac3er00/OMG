---
description: "Canonical OMG security pipeline with normalized findings, dependency enrichment, and untrusted-content evidence."
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(pytest:*), Bash(rg:*)
argument-hint: "[path or '.' for the current project]"
---

# /OMG:security-check — Canonical Security Pipeline

Run OMG's canonical security pipeline against the current project or a scoped path.

## Usage

```text
/OMG:security-check
/OMG:security-check .
/OMG:security-check app/
```

## What It Produces

- normalized findings across policy, Python AST checks, and dependency health
- evidence-ready provenance and trust scores
- a structured result that can be reused by `ship`, the control plane, and the OMG MCP

## Notes

- Use this for auth, secrets, untrusted-content, or dependency-risk work.
- `omg secure --command ...` remains the low-level command-risk primitive, not the full audit surface.
