# Public Release Checklist

Use this checklist before making OMG public or cutting a release tag.

## Identity

- README, `package.json`, plugin manifests, and CLI version output agree on the version
- repo URL is `https://github.com/trac3r00/OMG`
- plugin and marketplace id are `omg`

## Public Safety

- `python3 scripts/check-omg-public-ready.py` passes
- no internal planning docs ship in `docs/plans/`
- no absolute local paths or stale internal path references remain

## Verification

- [ ] `python3 scripts/sync-release-identity.py --check` — authored surfaces in sync
- [ ] `python3 scripts/validate-release-identity.py --scope all --forbid-version <previous-version>` — full identity validation
- [ ] `python3 scripts/omg.py contract validate` passes
- [ ] `python3 scripts/omg.py compat gate --max-bridge 0 --output artifacts/omg-compat-gap.json` passes
- [ ] `python3 scripts/omg.py release readiness --channel dual --output-root artifacts/release` returns `status=ok`
- [ ] `python3 scripts/omg.py validate --format json` includes `plugin_compatibility` check
- `python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel public --output-root <tmp>` passes
- `python3 scripts/omg.py contract compile --host claude --host codex --host gemini --host kimi --channel enterprise --output-root <tmp>` passes
- `python3 scripts/omg.py release readiness --channel dual --output-root <tmp>` passes

## Forge v0.3

- [ ] The 5 Forge domain CLI commands and their expected outputs:
  - `python3 scripts/omg.py forge vision-agent --preset labs` — exits 0, `agent_path: vision-agent`, `proof_backed: true`
  - `python3 scripts/omg.py forge robotics --preset labs` — exits 0, `agent_path: robotics`
  - `python3 scripts/omg.py forge algorithms --preset labs` — exits 0, `agent_path: algorithms`
  - `python3 scripts/omg.py forge health --preset labs` — exits 0, `agent_path: health`
  - `python3 scripts/omg.py forge cybersecurity --preset labs` — exits 0, `agent_path: cybersecurity`
- [ ] The `artifact_contracts` evidence fields are present:
  - `dataset_lineage`
  - `model_card`
  - `checkpoint_hash`
  - `regression_scoreboard`
  - `promotion_decision`
- [ ] Metadata fields are populated:
  - `context_checksum`
  - `profile_version`
  - `intent_gate_version`
- [ ] Adapter wrappers and their honest availability semantics:
  - `axolotl` (LLM finetuning)
  - `pybullet` (Physics sim)
  - `gazebo` (Robotics sim)
  - `isaac_gym` (RL environments)

## Verification

- Release readiness fails with machine-readable blockers unless all execution primitives are present and valid:
  - run coordinator state: `.omg/state/release_run_coordinator/<run_id>.json`
  - TDD proof-chain lock evidence: `.omg/state/test-intent-lock/*.json` (linked to run id or lock id)
  - rollback manifest: `.omg/state/rollback_manifest/*.json`
  - session health state: `.omg/state/session_health/<run_id>.json`
  - council verdicts: `.omg/state/council_verdicts/<run_id>.json`
  - Forge starter proof (`proof_backed: true`): `.omg/evidence/forge-specialists-*.json`
- Release readiness output exposes primitive evidence paths in `checks.execution_primitives.evidence_paths`
- Truth bundles (`claim-judge`, `test-intent-lock`, `proof-gate`) are verified and present in `registry/bundles/`
- `plan-council` role is compiled and verified in `registry/bundles/`
- `python3 scripts/check-omg-standalone-clean.py` passes
- `./scripts/verify-standalone.sh` passes
- `python3 -m pytest tests -q` passes

## Docs

- README matches the current product surface
- install guides for Claude Code, Codex, and OpenCode are current
- OpenCode provider module exists at `runtime/providers/opencode_provider.py`
- proof page includes current verification evidence
- changelog includes the release entry

## Release Ops

- `package.json` version matches the tag you will create
- npm publishing credentials are configured for `publish-npm.yml`
- GitHub Actions required checks are green
