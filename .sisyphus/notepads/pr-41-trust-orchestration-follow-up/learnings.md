# Learnings — pr-41-trust-orchestration-follow-up

## [2026-03-08] Setup
- Branch: `feature/pr-41-trust-orchestration` branched from `release/v2.0.8`
- Working dir: `/Users/cminseo/Documents/scripts/Shell/OMG`
- PR #40 is open and MERGEABLE; PR #41 targets `release/v2.0.8` first, retarget to `main` after PR #40 merges

## Key Patterns
- EvidencePack v2 is canonical — no schema migration allowed
- New artifacts are sibling files referenced by path/hash under `.omg/evidence/`, `.omg/state/`, etc.
- Scan-first evidence lookup: scan `.omg/evidence`, `.omg/tracebank`, `.omg/evals`, `.omg/lineage`, `.omg/state`
- `judge_claim()` and `evaluate_test_delta()` must NOT be replaced — extend only
- Playwright adapter is optional: `OMG_ENABLE_PLAYWRIGHT_BUNDLE=1` env flag
- `verification_loop` is a pure policy helper — no autonomous execution

## Critical Import Constraint
- `runtime/contract_compiler.py:1931` imports `evaluate_test_delta()` from `runtime.test_intent_lock`
- `runtime/contract_compiler.py` also imports `judge_claim()` from `runtime.claim_judge`
- These must remain intact after Task 2 extensions

## [2026-03-08] Task 1 - evidence_query
- Added runtime/evidence_query.py scan-first read-only helpers across .omg/evidence, .omg/tracebank, .omg/evals, .omg/lineage, and .omg/state with malformed JSON skip behavior
- query_evidence() now supports filtering by run_id, trace_id, schema, and artifact kind without relying on evidence-link ledgers
- Added tests/runtime/test_evidence_query.py coverage for happy paths, empty/missing directories, malformed payload skipping, and helper accessors for trace/eval/lineage/state

## [2026-03-08] Task 2 - claim/test runtime workflows
- Added `judge_claims(project_dir, claims)` in `runtime/claim_judge.py` to resolve run_id via `get_evidence_pack`, synthesize evidence refs, call `judge_claim()`, write `.omg/evidence/claim-judge-<run_id>.json`, and aggregate verdicts (`fail` > `insufficient` > `pass`)
- Added `lock_intent(project_dir, intent)` and `verify_intent(project_dir, lock_id, results)` in `runtime/test_intent_lock.py` with lock files under `.omg/state/test-intent-lock/` and status outputs (`locked`, `ok`, `fail`, `missing_lock`)
- Extended runtime tests to cover additive workflows while keeping `judge_claim()` and `evaluate_test_delta()` behavior intact

## [2026-03-08] Task 3 - claim/test control-plane surfaces
- Added `claim_judge(payload)` to ControlPlaneService: extracts `claims` list, returns 400/INVALID_CLAIM_INPUT if missing/non-list, delegates to `judge_claims(project_dir, claims)`
- Added `test_intent_lock(payload)` to ControlPlaneService: dispatches on `action` field (lock/verify), validates required fields per action, returns 400 with specific error codes (INVALID_INTENT_INPUT, INVALID_INTENT_ACTION)
- Added 4 routes to `_POST_ROUTE_TABLE`: `/v2/trust/claim-judge`, `/v1/trust/claim-judge`, `/v2/trust/test-intent-lock`, `/v1/trust/test-intent-lock`
- Added `omg_claim_judge` and `omg_test_intent_lock` MCP tools following exact `@mcp.tool()` pattern
- Updated `_MCPOMGServerModule` Protocol in test file with new method signatures
- Pre-existing LSP errors (TempPathFactory, MCP object attributes) confirmed as not-our-problem — basedpyright Protocol limitation with dynamically loaded modules
- Import cycle diagnostic on service.py is pre-existing (same `runtime/__init__.py` chain as existing `runtime.security_check`)
- 48 tests pass across all 3 test files

## [2026-03-08] Task 4 - repro pack
- Added `runtime/repro_pack.py` with `build_repro_pack(project_dir, run_id)` to assemble deterministic sibling manifests at `.omg/evidence/repro-pack-<run_id>.json`
- ReproPack includes path+sha256 references for EvidencePack, trace stream filtered by `trace_ids`, eval output, lineage, security scans, browser traces, verification state, incident artifacts, and carries `unresolved_risks`
- Added `tests/runtime/test_repro_pack.py` covering happy path assembly, missing run-id error contract, and stable-reference-only manifest behavior (no duplicated payload content)
