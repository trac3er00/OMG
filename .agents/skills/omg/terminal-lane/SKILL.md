---
name: omg-terminal-lane
description: "Fail-closed Bash governance lane: request tool approval, enforce compliance attestation, and block execution when evidence is denied or stale."
---

# OMG Terminal Lane

Run `runtime/tool_fabric.py:ToolFabric.request_tool` before every Bash call. If denied, stop. Then enforce `runtime/compliance_governor.py:evaluate_governed_tool_request`; if attestation/evidence is stale, regenerate evidence and retry once, else fail closed.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/terminal-lane-{run_id}.json`
