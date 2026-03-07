# OMG Proof Surface

[![Compat Gate](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml/badge.svg)](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml)
[![npm version](https://img.shields.io/npm/v/%40trac3er%2Foh-my-god)](https://www.npmjs.com/package/@trac3er/oh-my-god)

## Verification Status

OMG keeps verification visible instead of burying it in implementation details.

- Runtime evidence root: `.omg/evidence/`
- Security-check artifacts: `.omg/evidence/security-check-*.json`
- Trust and external input artifacts: `.omg/evidence/trust-*.json`
- Trace records and evidence links: `.omg/tracebank/events.jsonl`, `.omg/tracebank/evidence-links.jsonl`
- Eval gate artifacts and trace links: `.omg/evals/latest.json`, `.omg/evals/history.jsonl`, `.omg/evals/trace-links.jsonl`
- Lineage manifests: `.omg/lineage/*.json`
- Release readiness output links these machine artifacts instead of prose-only pass counts.

## Provider Matrix

| Provider | Detect | Auth Check | MCP Config | Host Priority |
|----------|--------|------------|------------|---------------|
| Claude Code | host-native | host-native | yes | primary |
| Codex | yes | yes | yes | primary |
| Gemini | yes | yes | yes | supported |
| Kimi | yes | yes | yes | supported |

## Adoption Evidence

- Native setup writes `.omg/state/adoption-report.json`
- Native setup writes `.omg/state/cli-config.yaml`
- `OMG-only` and `coexist` are both covered in setup tests
- OMC, OMX, and Superpowers references stay limited to compatibility and adoption guidance

## HUD Artifact

![OMG HUD](assets/omg-hud.svg)

## Benchmark Tasks

Representative benchmark tasks for this release:

- host detection and auth wiring
- canonical security-check routing and evidence emission
- stdio OMG control MCP wiring
- adoption detection with overlapping ecosystems
- plugin install and uninstall correctness
- `crazy` orchestration smoke coverage

## Sample Transcripts

- Setup: [docs/transcripts/setup.md](transcripts/setup.md)
- Crazy: [docs/transcripts/crazy.md](transcripts/crazy.md)

## Release Discipline

- Public launch checklist: [docs/release-checklist.md](release-checklist.md)
- Changelog: [CHANGELOG.md](../CHANGELOG.md)
