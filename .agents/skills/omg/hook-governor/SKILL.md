---
name: omg-hook-governor
description: "Hook-governance lane that computes injection state per tool call and resolves precedence conflicts with fail-closed security-first ordering."
---

# OMG Hook Governor

For each tool call, evaluate injection need via `hooks/pre-tool-inject.py:should_inject`; then compute checklist state with `get_checklist_progress`. If hook precedence conflicts occur, apply fail-closed ordering: security hooks first, then policy injection, then budget hooks.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/state/ledger/tool-ledger.jsonl`
