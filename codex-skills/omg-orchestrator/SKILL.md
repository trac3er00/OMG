---
name: omg-orchestrator
description: Use when coordinating an OMG task inside Codex across discovery, provider routing, implementation, and verification, especially when the request spans multiple phases or multiple OMG surfaces.
metadata:
  short-description: Orchestrate an OMG workflow in Codex
---

# OMG Orchestrator

Use this skill when Codex should drive an OMG task end to end instead of mirroring a single `/OMG:*` command.

## Workflow

1. Read the relevant repo files before choosing a provider path.
2. Map the work to one of these targets:
   - `codex`: backend, debugging, security, algorithms
   - `gemini`: UI, layout, visual refinement, accessibility
   - `kimi`: long-context inspection, synthesis, local runtime analysis
   - `ccg`: combined `codex + gemini` for mixed frontend/backend work
3. Use `python3 scripts/omg.py teams --target <target> --problem "<goal>"` when OMG routing evidence is useful.
4. Keep Claude-host command packaging separate from Codex skill behavior. Do not mirror `/OMG:*` commands one-for-one.
5. Finish with explicit verification and evidence capture.

## When To Read More

- Read [references/workflow.md](references/workflow.md) when you need the Codex-specific OMG execution loop and escalation rules.

