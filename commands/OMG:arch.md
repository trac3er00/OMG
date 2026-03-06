---
description: "Inspect the Bun/TypeScript architecture surface and summarize module boundaries."
allowed-tools: Read, Grep, Glob, Bash(rg:*), Bash(find:*), Bash(bun:*)
argument-hint: "[optional focus area]"
---

# /OMG:arch

Use this command to inspect the current OMG architecture after the Bun cutover.

## Focus Areas

- `scripts/omg.ts` for CLI surface
- `hooks/*.ts` for Claude lifecycle enforcement
- `runtime/*.ts` for routing and release logic
- `control_plane/*.ts` for JSON API entrypoints
- `lab/*.ts`, `registry/*.ts`, and `omg_natives/*.ts` for supporting services

## Suggested scan

```bash
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) | sort
```

Summaries should call out:

- public entrypoints
- persistence under `.omg/`
- hook-to-runtime dependencies
- release and provider verification paths
