# Learnings — ice-cold-v2-2-1-domination-release

## [2026-03-13T18:56] Session Init

### Baseline test state (ALL PASS):
- `tests/runtime/test_exec_kernel.py` + `test_worker_watchdog.py`: 34 passed
- `test_context_engine.py + test_tool_fabric.py + test_host_parity.py + test_release_chaos.py + tests/hooks/test_tdd_gate.py`: 53 passed

### Key directories:
- `runtime/` — core runtime modules
- `hooks/` — pre/post tool hooks
- `registry/bundles/` — YAML lane manifests
- `tests/runtime/` — test suite
- `hud/omg-hud.mjs` — HUD rendering
- `.github/workflows/` — CI: omg-compat-gate.yml, omg-release-readiness.yml, publish-npm.yml

### Runtime files in scope:
- `runtime/release_run_coordinator.py` — run_id spine
- `runtime/exec_kernel.py` — worker dispatch & isolation
- `runtime/worker_watchdog.py` — heartbeat & stall detection
- `runtime/merge_writer.py` — merge lock ownership
- `runtime/context_engine.py` — bounded packet builder
- `runtime/tool_fabric.py` — lane governance
- `runtime/team_router.py` — team dispatch

### Critical constraints (DO NOT VIOLATE):
- No container isolation promise (stays deferred)
- No new global modes
- No second context subsystem
- No stale/latest fallback for blocking release decisions
- Run-scoped evidence ONLY (keyed to active coordinator run_id)
- Music OMR remains the primary daily gate

## [2026-03-13] Task 1: Exec Kernel
- Centralized run registration on coordinator-resolved run_id in exec-kernel, including coordinator-active ownership snapshots.
- Bound merge authorization to both merge-writer lock owner and active coordinator run ownership; worktree mutations fail closed on mismatch.
- Added ownership metadata to watchdog heartbeat/replay evidence keyed by the same run_id spine.
- Preserved isolation policy: worktree mutating, none read-only, container deferred/unsupported with status=deferred and job_id=None.
- Added RED->GREEN tests covering coordinator run_id adoption, merge ownership metadata, and active-run mismatch blocking.

## [2026-03-13] Task 3: Chaos Suite
- Added `run_pressure_suite` to MusicOMRTestbed — structured pressure run returning determinism flag, unique hash, elapsed time, and ceiling check.
- Enhanced `emit_evidence` on MusicOMRTestbed to accept `trace_id` kwarg for traceability.
- Added `evidence_freshness` metadata to `build_chaos_replay_pack` — includes `generated_at`, `fixture_id`, `trace_id`, and optional `max_age_seconds`.
- New test `test_hello_no_subagent_spawn_and_bounded_context` proves release promise: trivial prompts get no subagent spawn and context stays within 1000-char budget.
- Enhanced `test_transposition_pressure_under_load` to use `run_pressure_suite`, validate replay evidence freshness metadata, emit OMR evidence with trace_id, and replay the pack.
- New test `test_transposition_pressure_ceiling_deterministic` proves determinism holds at the pressure ceiling (64 iterations).
- Fixture `transposition_pressure_fixture.json` expanded with `pressure_ceiling_iterations`, `evidence_freshness_max_age_seconds`, and `deterministic_seed`.
- All 10 chaos tests pass (8 existing + 2 new). Worker stall targeted run confirmed passing.
- Pattern: evidence_freshness on chaos packs enables downstream freshness assertions without wallclock flakiness.

## [2026-03-13] Task 4: Team Flow
- Added staged metadata to team routing (`team-plan -> team-exec -> team-verify -> team-fix`) and exposed canonical `/OMG:team` plus `/OMG:teams` compatibility alias metadata from `dispatch_team`.
- Moved clarification gating in both `execute_ccg_mode` and `execute_crazy_mode` ahead of worker launch by building context packets first and short-circuiting with `clarification_required` when unresolved.
- Added canonical `team` CLI subcommand in `scripts/omg.py` while keeping `teams` behavior unchanged for backward compatibility.
- Updated command contract in `commands/OMG:teams.md` to document staged flow and canonical alias usage.
- Hardened HUD verification rendering to show active-run scoped state only and explicit `verification: no active run` when no coordinator run is active.
- Added/updated tests for staged flow metadata, clarification-before-dispatch safety, and no-active-run HUD fallback handling.

## [2026-03-13] Task 5: Methodology Enforcement
- Mutation gate now fail-closes governed mutation-capable flows unless a coordinator-bound test lock, tool plan, and `done_when` criteria are all present.
- Coordinator spine binding now prioritizes `get_active_coordinator_run_id()` for mutation checks, preventing metadata run_id drift from bypassing lock/plan enforcement.
- Tool plan gate now enforces test lock + `done_when` only after existing clarification and council checks, preserving prior decision precedence while adding methodology proof requirements.
- Docs-only exemption behavior remains unchanged in mutation paths, and targeted coverage now includes `test_mutation_blocks_without_lock` and `test_docs_exemption_passes`.

## [2026-03-13] Task 7: Host Parity
- Release readiness now enforces four-host compile parity (claude, codex, gemini, kimi) as a blocking condition via manifest host checks.
- Host semantic parity reports are now required whenever canonical release hosts are in scope; missing reports block readiness.
- Added regression guard `test_regression_is_reported_as_drift` and explicit missing-report parity test to keep semantic drift release-blocking.
- OpenCode remains compatibility-only and non-blocking; compat snapshots now expose canonical versus compatibility-only host surfaces.

## [2026-03-13] Task 6: Tool Fabric
- Governed lane contracts now use semantic operations with explicit mutation promotion rules: `hash-edit` is hash-bound single-file mutation, `lsp-pack` is read-only by default, and `ast-pack` is dry-run-first unless promoted.
- Mutation-capable operations now require run-bound signed approval plus run-bound attestation metadata before execution, with approval scope/digest binding to the active `run_id`.
- Evidence requirements are now run-scoped (`{run_id}` paths) and freshness-checked (`generated_at` + max age), and mutation lanes fail closed on stale or mismatched run metadata.
- Added RED->GREEN coverage for approved governed execution with fresh evidence and for fail-closed mutation blocking on missing attestation or stale evidence.


## [2026-03-13] Task 8: Zero-Failure Hardening
- Hardened release-readiness execution primitive checks to fail closed on stale evidence, run_id mismatches, and excluded-failures lists without a signed waiver artifact.
- Enforced strict verification state semantics (`schema_version==2`, valid status, optional run_id match) and fixed proof-chain publishing to record background state under evidence `run_id`.
- Aligned workflow gates so compat/readiness block publish for the same release surface, while plugin diagnostics remain advisory.
