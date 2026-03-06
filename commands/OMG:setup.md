---
description: "Interactive setup for the Bun runtime, provider status, and Claude hook installation."
allowed-tools: Read, Write, Edit, Bash(bun:*), Bash(ls:*), Bash(grep:*)
argument-hint: "[optional: --non-interactive for CI mode]"
---

# /OMG:setup

Guided setup for the Bun runtime.

## Covers

- Bun availability and version
- provider detection and status via `runtime/provider_bootstrap.ts`
- standalone install or plugin install through `OMG-setup.sh`
- settings merge and hook registration

## Non-interactive mode

```bash
./OMG-setup.sh install --non-interactive
```
