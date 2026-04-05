---
name: omg-preflight
description: "Deterministic route-selection lane that resolves ambiguous risk classes to the strictest path and records tool/evidence plans before execution."
---

# OMG Preflight

Compute route with `runtime/preflight.py:run_preflight`. If multiple high-risk categories are triggered, select the strictest route and force security check; if route selection cannot resolve cleanly, fail closed. Record selected route, required tools, and evidence plan in trace metadata before proceeding.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/tracebank/events.jsonl`
