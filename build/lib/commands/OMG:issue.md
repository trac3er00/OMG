---
description: "Active red-team diagnostics and simulation surface for ranked issue triage."
allowed-tools: Read, Grep, Glob, Bash(python3 scripts/omg.py issue:*), Bash(pytest:*)
argument-hint: "[optional: --surfaces <csv> --simulate-surface <name> --simulate-scenario <name>]"
---

# /OMG:issue

Run active, read-only diagnostics across live and governed OMG surfaces, then emit ranked machine-readable issues.

## Command Roles

- `/OMG:issue` is the diagnostic and red-team simulation surface.
- `omg fix --issue` remains the issue-driven fix surface.
- Both share the same backend: `runtime/issue_surface.py`.
- `/OMG:issue` does not mutate targets.

## Surfaces Scanned

- `live_session`
- `forge_runs`
- `hooks`
- `skills`
- `mcps`
- `plugin_interop`
- `governed_tools`
- `domain_pipelines`

## Severity and Approval

- Severities: `critical`, `high`, `medium`, `low`, `info`
- High/critical issues must declare signed-approval requirements before fix execution.
- Output includes fix guidance plus evidence links for replay and audit.

## Usage

```text
/OMG:issue
/OMG:issue --surfaces plugin_interop,governed_tools
/OMG:issue --simulate-surface hooks --simulate-scenario "delete protected lock"
```

## Backend Output

- Evidence file: `.omg/evidence/issues/<run_id>.json`
- Report schema: `IssueReport`
- Each issue includes:
  - `id`
  - `severity`
  - `surface`
  - `title`
  - `description`
  - `fix_guidance`
  - `evidence_links`
  - `approval_required`
  - `approval_reason`
