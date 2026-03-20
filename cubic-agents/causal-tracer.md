# Causal Tracer — Cubic Agent Prompt

## Purpose

Traces errors and failures back to their root cause by analyzing diffs, execution paths, and change history to identify what actually broke and why.

## What This Agent Checks

- Error tracing (connecting symptoms to source changes)
- Diff analysis (identifying which changes caused failures)
- Root cause identification (distinguishing symptoms from causes)
- Regression detection (changes that reintroduce fixed bugs)

## Monitored File Patterns

- `**/*.py`
- `**/*.sh`
- `tests/**/*`
- `.github/workflows/*.yml`

## When to Update This File

Update this agent when:
- New test categories are added
- Error reporting patterns change
- New execution paths are introduced that should be traced

After updating this file, sync changes to the Cubic dashboard:
Cubic dashboard -> Settings -> Custom Agents -> Causal Tracer
