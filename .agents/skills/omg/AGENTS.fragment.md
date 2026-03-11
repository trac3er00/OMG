# OMG Codex Governance (channel: public)

## Build & Test

```bash
python3 -m pytest tests -q
python3 scripts/omg.py contract validate
python3 scripts/omg.py contract compile --host codex --channel public
```

## Protected Paths

The following paths require tier-gated review before mutation:

- `.omg/**`
- `.agents/**`
- `.codex/**`
- `.claude/**`

## Release Audit

Release readiness requires claim and compliance outcomes:

- `claim_judge`
- `compliance_governor`
- `execution_primitives`
Attestation requirements:
- `registry.verify_artifact.sign_artifact_statement`
- `registry.verify_artifact.verify_artifact_statement`

## Evidence Contract

Every production action must emit evidence containing these fields:

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

Council planning skills are protected and explicit-invocation only:

- `omg/plan-council`

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
- Require explicit invocation for protected production planning skills.
