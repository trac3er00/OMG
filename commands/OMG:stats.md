---
description: "Display session analytics, tool usage trends, file hotspots, and failure patterns."
allowed-tools: Read, Bash(bun:*), Grep
argument-hint: "[weekly|files|failures|dashboard]"
---

# /OMG:stats

Use this command to inspect analytics artifacts produced by the Bun hook stack.

## Primary data locations

- `.omg/state/ledger/`
- `.omg/evidence/`
- `.omg/state/failure-tracker.json`

## Typical checks

- current run summary and recent evidence packs
- failure hotspots emitted by `hooks/circuit-breaker.ts`
- file-level activity recorded by hook ledgers
- dashboard artifacts under `.omg/state/`

The command is read-oriented and should not mutate tracked state except when explicitly generating a dashboard artifact under `.omg/state/`.
