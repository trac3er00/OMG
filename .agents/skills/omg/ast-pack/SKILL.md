---
name: omg-ast-pack
description: "Two-phase AST lane that requires search before rewrite, dry-run evidence before promotion, and governed approval for mutation-capable edits."
---

# OMG AST Pack Lane

Execute AST work in two phases: search first, then rewrite. Resolve operation using `runtime/tool_fabric.py:ToolFabric._parse_semantic_operations`; if operation parsing fails or dry-run evidence is missing, stop. Require promotion through `ToolFabric.request_tool` before mutation-capable edits.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/ast-pack-{run_id}.json`
