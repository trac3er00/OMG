# OMG Codex Governance (channel: enterprise)

## Build & Test

```bash
python3 -m pytest tests -q
python3 scripts/omg.py contract validate
python3 scripts/omg.py contract compile --host codex --channel enterprise
```

## Protected Paths

Tier-gated review is required before mutating:

- `.omg/**`
- `.agents/**`
- `.codex/**`
- `.claude/**`

## Release Audit

Release readiness requires these outcomes:

- `claim_judge`
- `compliance_governor`
- `execution_primitives`
  Attestation requirements:
- `registry.verify_artifact.sign_artifact_statement`
- `registry.verify_artifact.verify_artifact_statement`

## Evidence Contract

Production actions must emit evidence with:

- `attestation_statement`
- `attestation_verifier`
- `claim_judge_verdict`
- `compliance_verdict`
- `executor`
- `lineage`
- `timestamp`
- `trace_id`

## Required Skills

- `omg/control-plane`
- `omg/mcp-fabric`

## Protected Planning Surface

Protected planning skills require explicit invocation:

- `omg/plan-council`

## Web Search Policy

- Prefer cached results over live network requests.
- Do NOT initiate live web searches unless explicitly instructed.
- Use `context7` or local documentation before external lookups; default to `cached_web_search: prefer_cached`.

## Approval Constraints

- Destructive file operations require explicit user approval.
- `git push --force` and branch deletions require approval.
- Production deployments require explicit approval.
- Mutations to protected paths require tier-gated approval.

## Instant Mode

- `/OMG:instant` — quick-start instant mode via `npx omg instant` for zero-config host bootstrap.

## Rules & Automations

- Rules: `protected_paths, explicit_invocation`
- Automations: `contract-compile, release-readiness`
- Respect the repo's `AGENTS.md` / `AGENTS.override.md` chain before OMG guidance.
- Keep OMG guidance separate from Codex built-in slash commands.
- Protected production planning skills stay explicit-invocation only.
