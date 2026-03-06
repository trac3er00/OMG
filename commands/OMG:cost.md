---
description: "Summarize current cost controls and budget evidence."
allowed-tools: Read, Grep, Glob, Bash(rg:*), Bash(cat:*), Bash(bun:*)
argument-hint: "[summary|ledger|limits]"
---

# /OMG:cost

Cost enforcement in the Bun runtime is centered on the budget hooks and `.omg` ledger output.

## Sources

- `hooks/_budget.ts`
- `hooks/tool-ledger.ts`
- `.omg/state/ledger/`

## Checks

- verify the budget hook is still registered in `settings.json`
- inspect any emitted ledger files under `.omg/state/ledger/`
- confirm release evidence includes unresolved risk and test coverage when cost controls tighten autonomy
