# Learnings — phase-1-release

## [2026-03-10] Session Start
- Plan approved by Momus after 2 review cycles
- TDD enforced: write failing tests first, then implement
- Runtime boundary: real execution when deps/hardware exist; otherwise emit explicit unavailable-backend evidence and block promotion
- Compliance boundary: repo-local and blocking via local policy bundles, tool gates, preset rules, provider allowlists — NO live provider terms lookups
- Storage: local-first SQLite (sqlite-vec + FTS5), adjacency-table lineage, filesystem artifacts; NO Lance branching in Phase 1
- Preset duplication: `hooks/setup_wizard.py` and `runtime/adoption.py` both define preset features — must consolidate to single source
- `build/lib/**` is a mirror tree — never write source-of-truth logic there
- Isaac Lab requires CUDA — NO CPU-only path; must add MockIsaacEnv for CI/dev
- GRPO/GDPO in Axolotl requires vLLM sidecar on separate GPUs
- `claim_judge` is evidence-aware but NOT wired into release gate — must fix in Task 1
- `lab/pipeline.py` still uses `simulated_metric` — primary target for Task 9
- Adapters return stub `invoked` responses — must upgrade in Tasks 7, 8

## [2026-03-10] Task 1 — Compliance Governor Authority
- Central precedence now lives in `runtime/compliance_governor.py` and delegates instead of duplicating existing policy sources.
- `tool_plan_gate` now routes allow/block decisions through Compliance Governor while preserving clarification and council semantics.
- `release_run_coordinator.finalize()` now executes programmatic compliance evaluation; if release claims are provided, `claim_judge` verdicts can block final status.
- `registry.verify_artifact.verify_artifact` is reused by Compliance Governor for artifact trust checks; no parallel verifier added.

## [2026-03-10] Task 2 — Deterministic Engine Contract
- `runtime/forge_run_id.py` now provides explicit deterministic contract derivation from `run_id` (`derive_run_seed`, `build_deterministic_contract`) with a same-hardware determinism scope.
- `runtime/repro_pack.py` now rejects EvidencePack inputs missing deterministic metadata and persists `seed`, `temperature_lock`, `determinism_version`, and `determinism_scope` into replay manifests.
- `runtime/proof_chain.py` now treats release/promotion claims as deterministic-required paths and blocks missing or mismatched deterministic metadata.
- `runtime/context_engine.py` now persists deterministic contract metadata in the session packet so run-scoped state and replay surfaces share the same contract.

## [2026-03-10] Task 3 - Agentic Storage Foundation
- SQLite-first MemoryStore works as primary backend with legacy JSON path fallback for compatibility.
- Run/profile scoping is now explicit on memory writes and reads, including scoped query and hybrid retrieval APIs.
- Large artifact access is now handle-oriented via index_artifact/query_artifacts; payloads are omitted and marked with omitted_payload.
- Lineage traversal now uses adjacency tables in .omg/lineage/adjacency.sqlite3 with scoped BFS traversal.
- Context engine packets now expose artifact_handles alongside artifact_pointers, preserving bounded non-inline payload behavior.

## Evidence Profiles and Forge Contracts (Task 4)
- Expanded evidence profiles to include `browser-flow`, `forge-cybersecurity`, `interop-diagnosis`, `install-validation`, and `buffet`.
- Replaced placeholder Forge artifact contracts with concrete schema requirements (lineage_hash, model_id, sha256, score, decision_id).
- Enforced non-placeholder status for artifacts in the promotion path.
- Verified that existing evidence helpers correctly resolve new profiles.

## Real Artifact Attestor (Task 5)
- `registry/verify_artifact.py` now emits and validates offline in-toto/SLSA-style statements using stdlib HMAC-SHA256 with signer metadata, subject digests, and timestamps.
- `verify_artifact` now treats missing/invalid attestation statements as untrusted in the default local flow instead of relying on signer+checksum alone.
- `scripts/validate-release-identity.py` now blocks promotion manifests that omit signed attestations or contain digest/signature mismatches.
- `runtime/proof_chain.py` and `runtime/repro_pack.py` now carry attestation statement references/artifacts when present for replay and proof-chain traceability.

## Sandboxed Forge Runner (Task 6)
- Added `lab/forge_runner.py` with `ForgeRunSpec`/`ForgeRunResult` and `run_forge_sandboxed()` that enforces time/cost/GPU/outbound budgets while emitting isolation + budget evidence for each run.
- Extended `tools/python_sandbox.py` with `execute_budgeted_run()` and isolated subprocess execution helper to support trainer + optional sidecar multi-process contracts and checkpoint extraction.
- Added trust evidence bridge `write_sandbox_budget_evidence()` in `runtime/untrusted_content.py` and reused secure-worktree execution cues via `runtime/subagent_dispatcher.resolve_execution_boundary()`.
- Added tests proving multiprocess evidence behavior and outbound/GPU budget blocking in `tests/tools/test_python_sandbox.py` and `tests/security/test_repl_sandbox.py`.
- Captured required QA artifacts in `.sisyphus/evidence/task-6-sandboxed-runner.txt` and `.sisyphus/evidence/task-6-sandboxed-runner-error.txt`.

## Live Axolotl Adapter (Task 7)
- Axolotl adapter now resolves explicit modes (`preflight`, `live_sft`, `live_grpo`, `live_gdpo`) with deterministic default routing based on `reward_heads`.
- Bounded hyperparameter search now emits exactly 6 deterministic scored trials per run from the curated search space and records best-trial evidence.
- Live training path now runs through sandboxed forge runner and emits checkpoint artifact metadata, sidecar evidence paths for GRPO/GDPO, and run-scoped adapter evidence JSON.
- Resume protection now blocks unsafe flows for missing checkpoint path, incompatible checkpoint formats, and LoRA double-adapter stacking.
- Adapter registry/agent contract now carries unavailable backend evidence (`unavailable_backend`, `axolotl_not_installed`) while preserving optional-backend non-blocking behavior unless backend is explicitly required.

## Simulator Backends + MockIsaacEnv (Task 8)
- `lab/pybullet_adapter.py` now executes bounded local episodes in live mode when PyBullet is available and always emits `backend`, `seed`, `episode_stats`, and `replay_metadata` fields.
- `lab/gazebo_adapter.py` is now explicitly marked as a `validation_fidelity` backend and emits fidelity-scoped simulator evidence instead of throughput-style defaults.
- `lab/isaac_gym_adapter.py` remains the public compatibility hook but now targets Isaac Lab semantics: live requires CUDA + Isaac Lab and missing prerequisites return `unavailable_backend` with reason `isaac_lab_requires_cuda`.
- Added `lab/mock_isaac_env.py` with deterministic seedable `reset`, `step`, `render`, and `close` behavior for CPU-only CI/dev tests.
- `runtime/forge_agents.py` now executes simulator adapter hooks directly, preserves required-backend blocking, and converts optional `unavailable_backend` results into `skipped_unavailable_backend` with `promotion_blocked=False`.
- Captured QA evidence in `.sisyphus/evidence/task-8-simulator-backends.txt` and `.sisyphus/evidence/task-8-simulator-backends-error.txt`.

## Buffet Preset and Preset Consolidation (Task 10)
- `runtime/adoption.py` is now the single source of truth for preset ordering (PRESET_ORDER), levels (PRESET_LEVEL), and feature flags (PRESET_FEATURES).
- `hooks/setup_wizard.py` no longer defines its own PRESET_ORDER or _PRESET_LEVEL — both are imported from adoption.py. Identity check (`is`) confirms same object, not a copy.
- Buffet preset adds 6 new managed flags: DATA_ENFORCEMENT, WEB_ENFORCEMENT, TERMS_ENFORCEMENT, COUNCIL_ROUTING, FORGE_ALL_DOMAINS, NOTEBOOKLM. All True for buffet, all False for lower presets.
- NotebookLM MCP catalog entry now has `min_preset: "buffet"` so it auto-includes only at buffet tier.
- `settings.json` trust_tiers now includes buffet at level 4 with `council_validated` source.
- Pre-existing e2e failures (2 tests) caused by missing `registry` module in portable runtime tree — unrelated to preset work.
- xdist parallelism causes spurious e2e failures; running without xdist reduces false positives.
