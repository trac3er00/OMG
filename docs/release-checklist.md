# Public Release Checklist

Use this checklist before making OMG public or cutting a release tag.

## Identity

- README, `package.json`, plugin manifests, and CLI version output agree on the version
- repo URL is `https://github.com/trac3er00/OMG`
- plugin and marketplace id are `omg`

## Public Safety

- `python3 scripts/check-omg-public-ready.py` passes
- no internal planning docs ship in `docs/plans/`
- no absolute local paths or stale internal path references remain

## Verification

- `python3 scripts/sync-release-identity.py --check` passes (canonical version parity across all tracked surfaces)
- `python3 scripts/omg.py contract validate` passes
- `python3 scripts/omg.py contract compile --host claude --host codex --channel public --output-root <tmp>` passes
- `python3 scripts/omg.py contract compile --host claude --host codex --channel enterprise --output-root <tmp>` passes
- `python3 scripts/omg.py release readiness --channel dual --output-root <tmp>` passes
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
- install guides for Claude Code and Codex are current
- proof page includes current verification evidence
- changelog includes the release entry

## Release Ops

- `package.json` version matches the tag you will create
- npm publishing credentials are configured for `publish-npm.yml`
- GitHub Actions required checks are green
