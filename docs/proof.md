# OMG Proof Surface

[![Compat Gate](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml/badge.svg)](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml)
[![npm version](https://img.shields.io/npm/v/%40trac3er%2Foh-my-god)](https://www.npmjs.com/package/@trac3er/oh-my-god)

<!-- OMG:GENERATED:proof-quickstart -->
## Getting Started with Proof

```bash
omg proof open --html       # open latest evidence pack as narrated proof
omg blocked --last          # inspect last governance block explanation
omg explain run <id>        # explain a specific run
omg budget simulate --enforce
```

Machine-generated evidence artifacts: `.omg/evidence/`
<!-- /OMG:GENERATED:proof-quickstart -->

## Verification Status

OMG keeps verification visible instead of burying it in implementation details.

- Runtime evidence root: `.omg/evidence/`
- Doctor output: `.omg/evidence/doctor.json`
- Plugin diagnostics: `.omg/evidence/plugin-diagnostics.json` (via `diagnose-plugins`)
- Security-check artifacts: `.omg/evidence/security-check-*.json`
- Trust and external input artifacts: `.omg/evidence/trust-*.json`
- Truth bundles:
  - `claim-judge`: `.omg/evidence/claim-judge-*.json` (verifies claim-to-evidence mapping)
  - `test-intent-lock`: `.omg/evidence/test-intent-lock-*.json` (verifies test-to-intent alignment)
  - `proof-gate`: `.omg/evidence/proof-gate-*.json` (verifies final release readiness)
- Release execution primitives required by `omg release readiness`:
  - canonical evidence profile registry: `runtime.evidence_requirements.EVIDENCE_REQUIREMENTS_BY_PROFILE` (release-facing labels derive from this map)
  - run coordinator state: `.omg/state/release_run_coordinator/<run_id>.json`
  - TDD lock evidence: `.omg/state/test-intent-lock/*.json`
  - rollback manifest: `.omg/state/rollback_manifest/*.json`
  - session health: `.omg/state/session_health/<run_id>.json`
  - council verdicts: `.omg/state/council_verdicts/<run_id>.json`
  - Forge starter proof (`proof_backed: true`): `.omg/evidence/forge-specialists-*.json`
  - exec kernel state: `.omg/state/exec-kernel/<run_id>.json`
  - worker watchdog replay: `.omg/evidence/subagents/<run_id>-replay.json`
  - merge writer provenance: `.omg/evidence/merge-writer-<run_id>.json`
  - tool fabric ledger: `.omg/state/ledger/tool-ledger.jsonl`
  - budget envelope state: `.omg/state/budget-envelopes/<run_id>.json`
  - issue report: `.omg/evidence/issues/<run_id>.json`
  - host parity report: `.omg/evidence/host-parity-<run_id>.json`
  - music OMR testbed evidence: `.omg/evidence/music-omr-<run_id>.json`

## Permanent Music OMR Daily Gate

Music OMR is the permanent daily release gate artifact. Release readiness requires a fresh Music OMR evidence file tied to the active run id.

- Gate cadence: daily scheduled run via `.github/workflows/omg-release-readiness.yml`
- Run scope: `run_id` must match the active release evidence pack run
- Freshness metadata: `freshness.generated_at`, `freshness.max_age_seconds`, `freshness.expires_at`, `freshness.is_fresh`
- Fixture inventory: `fixture_inventory` must include deterministic fixture ids (for this gate: `simple_c_major.json`, `simple_g_major.json`, `chromatic_fragment.json`, `waltz_three_four.json`, `transposition_pressure_fixture.json`); minimum 5 fixtures required (`fixture_inventory_valid` must be `true`)
- Trace metadata: `trace.trace_id`, `trace.gate=music-omr-daily`, `trace.run_scope=release-run`, `trace_metadata.testbed`, `trace_metadata.fixture_count`, `trace_metadata.run_id_linkage`
- Freshness threshold: `freshness_threshold_secs`, `freshness.freshness_threshold_secs`
- Run linkage: `run_id` must match the active release run, `trace_metadata.run_id_linkage` must equal `run_id`

## Forge v0.3 Evidence

Forge v0.3 introduces richer evidence artifacts for domain-specific training and evaluation.

- Forge starter proof: `.omg/evidence/forge-specialists-{run_id}.json`
- Artifact contracts schema:
  - `dataset_lineage`: provenance for training data
  - `model_card`: model metadata and intended use
  - `checkpoint_hash`: integrity for model weights
  - `regression_scoreboard`: evaluation results vs baselines
  - `promotion_decision`: automated or human-in-the-loop release signal
- Domain pack enforcement: Forge ensures that domain-specific constraints (e.g., robotics safety, algorithm determinism) are satisfied before emitting a release-ready claim.

- Release readiness machine output includes `checks.execution_primitives` with `missing`, `invalid`, and `evidence_paths`
- Browser evidence: `.omg/evidence/browser-*.png` and `.omg/evidence/browser-*.json` (Playwright-backed verification)
- Canonical browser command: `/OMG:browser` with `/OMG:playwright` as a compatibility alias
- Trace records and evidence links: `.omg/tracebank/events.jsonl`, `.omg/tracebank/evidence-links.jsonl`
- Eval gate artifacts and trace links: `.omg/evals/latest.json`, `.omg/evals/history.jsonl`, `.omg/evals/trace-links.jsonl`
- Lineage manifests: `.omg/lineage/*.json`
- Release readiness output links these machine artifacts instead of prose-only pass counts.

## Provider Matrix

| Provider | Tier | Detect | Auth Check | MCP Config | Host Priority |
|----------|------|--------|------------|------------|---------------|
| Claude Code | Canonical | host-native | host-native | yes | primary |
| Codex | Canonical | yes | yes | yes | primary |
| Gemini | Canonical | yes | yes | yes | primary |
| Kimi | Canonical | yes | yes | yes | primary |
| OpenCode | Compatibility-only | yes | yes | yes | supported |

## Adoption Evidence

- Native setup writes `.omg/state/adoption-report.json`
- Native setup writes `.omg/state/cli-config.yaml`
- Plugin allowlist: `.omg/state/plugins-allowlist.yaml`
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
