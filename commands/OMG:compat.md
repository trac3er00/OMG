---
description: Run legacy skill names on OMG standalone via the Bun compatibility dispatcher.
allowed-tools: Read, Grep, Glob, Bash(bun:*), Bash(rg:*), Bash(find:*), Bash(cat:*)
argument-hint: "<skill-name> [optional problem]"
---

# /OMG:compat

Use this when migrating legacy workflows to OMG standalone.

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.ts}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.ts" ]; then OMG_CLI="scripts/omg.ts"; fi
```

## List supported skills

```bash
bun "$OMG_CLI" compat list
```

## Inspect contracts and gates

```bash
bun "$OMG_CLI" compat contract --all
bun "$OMG_CLI" compat contract --skill omg-teams
bun "$OMG_CLI" compat snapshot --output runtime/omg_compat_contract_snapshot.json
bun scripts/check-omg-compat-contract-snapshot.ts --strict-version
bun scripts/check-omg-standalone-clean.ts
```

## Generate a compatibility gap report

```bash
bun "$OMG_CLI" compat gap-report
```

## Enforce the GA gate

```bash
bun "$OMG_CLI" compat gate --max-bridge 0
bun "$OMG_CLI" compat gate --max-bridge 0 --output .omg/evidence/omg-compat-gap.json
```

## Run a legacy skill

```bash
bun "$OMG_CLI" compat run --skill "<skill-name>" --problem "$ARGUMENTS"
```
