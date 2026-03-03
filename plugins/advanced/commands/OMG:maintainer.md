---
description: Open-source maintainer workflow — issue triage, release notes, review assistance, impact evidence pack
allowed-tools: Read, Write, Edit, MultiEdit, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(ls:*)
argument-hint: "[triage|release|review|impact]"
---

# /OMG:maintainer — OSS Maintainer Kit

## Modes
1. `triage`: summarize new issues, propose labels/priority/owner.
2. `release`: draft release notes from recent commits and notable changes.
3. `review`: review open changes with risk tags and test gaps.
4. `impact`: generate Ecosystem Impact evidence draft.

## Ecosystem Impact Evidence Pack
Create `.omg/evidence/oss-impact.json` with:
- `activity`: commits/reviews/releases in recent window
- `dependents`: direct/transitive usage indicators (if available)
- `stability`: test pass/fail trend and security findings
- `adoption_signals`: downloads/stars/changelog cadence (factual only)
- `summary_500_words`: draft narrative for application forms

## Integrity Policy
- Never fabricate stats.
- Never suggest metric manipulation (stars/download inflation).
- Mark unknown metrics as `unverified`.

## Output format
- Findings first
- Risks and unknowns
- Actionable next 3 maintainer tasks
