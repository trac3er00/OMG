# OMG Codex Governance (channel: enterprise)

## Build & Test

```bash
python3 -m pytest tests -q
python3 scripts/omg.py contract validate
python3 scripts/omg.py contract compile --host codex --channel enterprise
```

## Protected Paths

The following paths require tier-gated review before mutation:

- `.omg/**`
- `.agents/**`
- `.codex/**`
- `.claude/**`

## Evidence Contract

Every production action must emit evidence containing these fields:

- `executor`
- `lineage`
- `timestamp`
- `trace_id`

## Required Skills

- `omg/control-plane`
- `omg/mcp-fabric`

## Web Search Policy

- Prefer cached results over live network requests.
- Do NOT initiate live web searches unless explicitly instructed.
- Use `context7` or local documentation before external lookups.
- Set `cached_web_search: prefer_cached` as the default.

## Approval Constraints

- Destructive file operations require explicit user approval.
- `git push --force` and branch deletions require explicit approval.
- Production deployments require explicit approval.
- Mutations to protected paths require tier-gated approval.

## Rules & Automations

- Rules: `protected_paths, explicit_invocation`
- Automations: `contract-compile, release-readiness`
- Require explicit invocation for production-control-plane skills.
