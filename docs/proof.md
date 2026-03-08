# OMG Proof Surface

[![Compat Gate](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml/badge.svg)](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml)
[![npm version](https://img.shields.io/npm/v/%40trac3er%2Foh-my-god)](https://www.npmjs.com/package/@trac3er/oh-my-god)

## Verification Status

OMG keeps verification visible instead of burying it in implementation details.

- Runtime evidence root: `.omg/evidence/`
- Doctor output: `.omg/evidence/doctor.json`
- Security-check artifacts: `.omg/evidence/security-check-*.json`
- Trust and external input artifacts: `.omg/evidence/trust-*.json`
- Truth bundles:
  - `claim-judge`: `.omg/evidence/claim-judge-*.json` (verifies claim-to-evidence mapping)
  - `test-intent-lock`: `.omg/evidence/test-intent-lock-*.json` (verifies test-to-intent alignment)
  - `proof-gate`: `.omg/evidence/proof-gate-*.json` (verifies final release readiness)
- Browser evidence: `.omg/evidence/browser-*.png` and `.omg/evidence/browser-*.json` (Playwright-backed verification)
- Trace records and evidence links: `.omg/tracebank/events.jsonl`, `.omg/tracebank/evidence-links.jsonl`
- Eval gate artifacts and trace links: `.omg/evals/latest.json`, `.omg/evals/history.jsonl`, `.omg/evals/trace-links.jsonl`
- Lineage manifests: `.omg/lineage/*.json`
- Release readiness output links these machine artifacts instead of prose-only pass counts.

## Provider Matrix

| Provider | Tier | Detect | Auth Check | MCP Config | Host Priority |
|----------|------|--------|------------|------------|---------------|
| Claude Code | Canonical | host-native | host-native | yes | primary |
| Codex | Canonical | yes | yes | yes | primary |
| Gemini | Compatibility | yes | yes | yes | supported |
| Kimi | Compatibility | yes | yes | yes | supported |

## Adoption Evidence

- Native setup writes `.omg/state/adoption-report.json`
- Native setup writes `.omg/state/cli-config.yaml`
- `OMG-only` and `coexist` are both covered in setup tests
- Canonical modes: `chill`, `focused`, `exploratory`
- OMC, OMX, and Superpowers references stay limited to compatibility and adoption guidance

## HUD Artifact

![OMG HUD](assets/omg-hud.svg)

## Benchmark Tasks

Representative benchmark tasks for this release:

- host detection and auth wiring
- canonical security-check routing and evidence emission
- narrowed stdio OMG control MCP wiring
- truth bundle verification (claim-judge, test-intent-lock, proof-gate)
- plan-council role compilation and execution
- adoption detection with overlapping ecosystems
- plugin install and uninstall correctness
- `crazy` orchestration smoke coverage

## Sample Transcripts

- Setup: [docs/transcripts/setup.md](transcripts/setup.md)
- Crazy: [docs/transcripts/crazy.md](transcripts/crazy.md)

## Release Discipline

- Public launch checklist: [docs/release-checklist.md](release-checklist.md)
- Changelog: [CHANGELOG.md](../CHANGELOG.md)
