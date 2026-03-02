---
description: Run legacy skill names on OAL standalone via compatibility dispatcher.
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(rg:*), Bash(find:*), Bash(cat:*)
argument-hint: "<skill-name> [optional problem]"
---

# /OAL:compat

Use this when migrating legacy workflows to OAL standalone.

```bash
OAL_CLI="${OAL_CLI_PATH:-$HOME/.claude/oal-runtime/scripts/oal.py}"
if [ ! -f "$OAL_CLI" ] && [ -f "scripts/oal.py" ]; then OAL_CLI="scripts/oal.py"; fi
```

## List supported skills

```bash
python3 "$OAL_CLI" compat list
```

## Inspect contracts

```bash
python3 "$OAL_CLI" compat contract --all
python3 "$OAL_CLI" compat contract --skill omc-teams
python3 "$OAL_CLI" compat snapshot --output runtime/oal_compat_contract_snapshot.json
python3 scripts/check-oal-compat-contract-snapshot.py --strict-version
python3 scripts/check-oal-standalone-clean.py
```

## Generate compatibility gap report

```bash
python3 "$OAL_CLI" compat gap-report
```

## Enforce GA gate (CI/local)

```bash
python3 "$OAL_CLI" compat gate --max-bridge 0
python3 "$OAL_CLI" compat gate --max-bridge 0 --output .oal/evidence/oal-compat-gap.json
```

## Run a legacy skill

```bash
python3 "$OAL_CLI" compat run --skill "<skill-name>" --problem "$ARGUMENTS"
```

Examples:

```bash
python3 "$OAL_CLI" compat run --skill omc-teams --problem "review auth flow"
python3 "$OAL_CLI" compat run --skill plan --problem "ship secure release"
python3 "$OAL_CLI" compat run --skill pipeline --problem "train model"
```
