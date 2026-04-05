---
name: omg-hash-edit
description: "Hash-bound edit lane that verifies digest constraints, refreshes approvals on mismatch, and aborts mutations until approval and evidence are valid."
---

# OMG Hash Edit Lane

Before Edit, validate digest via `runtime/tool_fabric.py:ToolFabric._check_hash_edit_constraints`. On hash mismatch: refresh target hash, produce a new approval via `ToolFabric.check_approval`, and abort mutation until approval and evidence both pass.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/hash-edit-{run_id}.json`
