---
description: Ship pipeline — Idea -> Plan -> Execute -> Evidence -> PR-ready summary
allowed-tools: Read, Write, Edit, MultiEdit, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(python3:*), Bash(pytest:*), Bash(npm test:*), Bash(go test:*), Bash(cargo test:*), Bash(jest:*), Bash(vitest:*)
argument-hint: "[goal or optional path to .oal/idea.yml]"
---

# /OAL:ship — Idea -> Evidence -> PR

## Step 1: Load idea contract
- Prefer `.oal/idea.yml`.
- If missing, scaffold from `~/.claude/templates/oal/idea.yml` and ask user for minimum fields:
  - `goal`, `constraints`, `acceptance`, `risk`, `evidence_required`.

## Step 2: Convert idea to execution plan
- Generate `.oal/state/_plan.md` and `.oal/state/_checklist.md`.
- Set explicit `CHANGE_BUDGET`.
- List source files, tests, and rollback strategy.

## Step 3: Execute with Shadow + Evidence discipline
- Implement changes.
- Run verification commands.
- Build an evidence pack at `.oal/evidence/<run-id>.json` containing:
  - `tests[]`, `security_scans[]`, `diff_summary`, `reproducibility`, `unresolved_risks[]`.

## Step 4: Security and trust checks
- Run `/OAL:security-review` for auth/payment/database/sensitive changes.
- If config/hook/MCP changes are involved, ensure trust manifest is updated at `.oal/trust/manifest.lock.json`.

## Step 5: PR-ready output
Return:
1. Goal and scope delivered
2. Files changed
3. Verification evidence (command + exit code)
4. Risks/unknowns
5. Suggested PR title + body

## Anti-patterns
- Do not claim done without evidence.
- Do not edit tests to hide product bugs.
- Do not skip trust review for `.claude/.oal` or MCP changes.
