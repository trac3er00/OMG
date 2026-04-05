---
name: omg-remote-supervisor
description: "Local supervisor session lane with per-request token verification, replay/staleness rejection, and evidence capture before worker dispatch."
---

# OMG Remote Supervisor

Issue session credentials via `runtime/remote_supervisor.py:issue_local_supervisor_session` and validate each inbound token with `verify_local_supervisor_token`. Reject mismatched signatures or stale timestamps; write session evidence before worker dispatch.

- Channel: `enterprise`
- Execution modes: `local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/supervisor/sessions/*.json`
