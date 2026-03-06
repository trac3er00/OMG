---
description: "Run Bun-era repository health checks."
allowed-tools: Bash(ls:*), Bash(cat:*), Bash(find:*), Bash(grep:*), Bash(git:*), Bash(which:*), Bash(head:*), Bash(wc:*), Bash(stat:*), Bash(bun:*), Read, Grep, Glob
argument-hint: "[quick|full]"
---

# /OMG:health-check

Run the standard Bun verification stack for OMG:

```bash
bun run typecheck
bun test
bun scripts/check-runtime-clean.ts
```

Quick review points:

- installed Bun version matches the repo requirement
- hook and runtime entrypoints in `settings.json` point at `.ts` files
- no retired runtime files remain under `hooks/`, `runtime/`, `scripts/`, `tools/`, `control_plane/`, or `omg_natives/`
