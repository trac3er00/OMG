---
description: Run legacy skill names on OMG standalone via compatibility dispatcher.
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(rg:*), Bash(find:*), Bash(cat:*)
argument-hint: "<skill-name> [optional problem]"
---

# /OMG:compat

Use this when migrating legacy workflows to OMG standalone.

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.py}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.py" ]; then OMG_CLI="scripts/omg.py"; fi
```

## List supported skills

```bash
python3 "$OMG_CLI" compat list
```

## Inspect contracts

```bash
python3 "$OMG_CLI" compat contract --all
python3 "$OMG_CLI" compat contract --skill omg-teams
python3 "$OMG_CLI" compat snapshot --output runtime/omg_compat_contract_snapshot.json
python3 scripts/check-omg-compat-contract-snapshot.py --strict-version
python3 scripts/check-omg-standalone-clean.py
```

## Generate compatibility gap report

```bash
python3 "$OMG_CLI" compat gap-report
```

## Enforce GA gate (CI/local)

```bash
python3 "$OMG_CLI" compat gate --max-bridge 0
python3 "$OMG_CLI" compat gate --max-bridge 0 --output .omg/evidence/omg-compat-gap.json
```

## Run a legacy skill

```bash
python3 "$OMG_CLI" compat run --skill "<skill-name>" --problem "$ARGUMENTS"
```

Examples:

```bash
python3 "$OMG_CLI" compat run --skill omg-teams --problem "review auth flow"
python3 "$OMG_CLI" compat run --skill plan --problem "ship secure release"
python3 "$OMG_CLI" compat run --skill pipeline --problem "train model"
```
