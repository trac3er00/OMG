# Learnings — post-v2-0-8-full-roadmap

## [2026-03-08] Session ses_334db12c0ffeMVWl5GpM3Gqtwx — Baseline Assessment

### Repo state at Wave 1 start
- Branch: `release/v2.0.8`
- HEAD: `dc0ba11` (chore: bump remaining version surfaces to 2.0.8)
- Contract validation: `status: ok`, version 2.0.8, 22 bundles, hosts: `claude`, `codex` only
- Baseline tests: `tests/runtime/test_proof_chain.py tests/runtime/test_claim_judge.py tests/runtime/test_proof_gate.py` → 10 passed

### Key architecture facts (from prior explore sessions)
- `registry/omg-capability.schema.json` line 44: host enum is `["claude","codex"]` — must expand to `["claude","codex","gemini","kimi"]` in Task 13
- `runtime/contract_compiler.py`: has `_compile_claude_outputs()` and `_compile_codex_outputs()` only; Task 14 adds `_compile_gemini_outputs()` and `_compile_kimi_outputs()`
- `hud/omg-hud.mjs` PRESET_CONFIGS: has `focused` preset — Task 4 renames to `standard` with backward-compat alias
- Evidence pipeline chain: `EvidencePack (shadow_manager.py)` → `ProofChain (proof_chain.py)` → `ProofGate (proof_gate.py)` → `ClaimJudge (claim_judge.py)` — all share ad-hoc `_as_*()` normalization helpers with NO version field
- `hooks/session-end-capture.py` is fire-and-forget — do NOT attach blocking verification to it
- `tools/python_sandbox.py` is REPL-only — Semgrep is external binary; must be optional with graceful fallback
- `lab/pipeline.py` is a stub with simulated metrics — forge task must work with existing stub as entry-point
- Session snapshot features (`OMG_SNAPSHOT_ENABLED`, `OMG_BRANCHING_ENABLED`, `OMG_MERGE_ENABLED`) all default `False`
- Gemini uses `~/.gemini/settings.json` (JSON, `httpUrl` key); Kimi uses `~/.kimi/mcp.json` (JSON, `type`/`url` keys)
- `plugins/dephealth/cve_scanner.py` has 24h cache + offline/disabled fallback — use this pattern for KEV/EPSS in Task 6

### Wave 1 parallelization plan
- Tasks 1, 3, 4 start in parallel (all unblocked, no file conflicts)
- Task 2 starts after Task 1 completes (blocked by 1)
- Task 1 files: proof_chain.py, shadow_manager.py, claim_judge.py, proof_gate.py, test fixtures
- Task 3 files: session_snapshot.py, state_migration.py, session command docs
- Task 4 files: adoption.py, runtime_profile.py, hud/omg-hud.mjs, OMG:mode.md

## [2026-03-08] Task 4 — Profile Taxonomy Collapse

- HUD presets now use `standard` as canonical config key/default, with `focused` retained only as alias input.
- Mode naming is split cleanly by surface: adoption presets stay `safe|balanced|interop|labs`, runtime concurrency stays `eco|balanced|turbo`, and canonical user-facing modes are reserved as `chill|focused|exploratory`.
- `/OMG:mode` docs now describe canonical mode names directly to avoid leaking HUD preset terminology into session mode semantics.
- E2E HUD coverage now asserts both canonical `standard` handling and backward-compatible `focused` alias equivalence.

## [2026-03-07] Task 1 — Evidence schema v2 foundation
- Added `schema_version: 2` emission in `hooks/shadow_manager.py:create_evidence_pack()` and introduced optional `artifacts` list on emitted EvidencePack payloads.
- Added `runtime/proof_chain.py:_normalize_evidence_pack()` adapter: missing `schema_version` is treated as v1 and accepted unchanged; v2 validates artifact records (`kind`, `path`, `sha256`, `parser`, `summary`, `trace_id`).
- Updated `assemble_proof_chain()` to emit `schema_version: 2` and normalized artifact-record arrays in ProofChain output; v1 evidence can still assemble without adapter errors.
- Added `runtime/claim_judge.py:_normalize_claim()` to accept both v1 top-level claim fields and v2 nested `evidence` shape; malformed artifact records now raise deterministic `ValueError` (e.g. `claim_artifact_missing_sha256`).
- Added `runtime/proof_gate.py` evidence-pack schema validator that accepts both v1 (no version) and v2 payloads, with v2 artifact-field checks.
- Added fixtures `tests/runtime/fixtures/evidence_v1_sample.json` and `tests/runtime/fixtures/evidence_v2_sample.json` and expanded runtime tests; targeted suite now passes at 15 tests.

## [2026-03-07] Task 3 — Snapshot Foundation Stabilization

### Key findings
- `detect_merge_conflicts` had a design bug: it compared ALL keys including branch metadata (`name`, `snapshot_id`, `created_at`). Different branches inherently have different values for these keys, so merges would ALWAYS produce conflicts. Fixed by introducing `_BRANCH_META_KEYS` frozenset and `_strip_branch_meta()` to exclude branch-level metadata from conflict detection.
- `fork_branch` was referenced in task specs and command docs (`OMG:session-fork.md`) but never implemented. It's a thin wrapper around `create_branch` that always requires a snapshot ID.
- `preview_merge` was the canonical function name but callers expected `merge_preview`. Added as alias.
- CLI had no `--help` handler — exited 1 on no args with usage on stderr. Added `--help`/`-h` that prints to stdout and exits 0.
- Migration map in `state_migration.py` was missing entries for `current_branch.json` and `branches/` directory.
- Pre-existing LSP errors in `test_omg_mcp_server.py`, `mcp_memory_server.py`, `state_migration.py:154` — all pre-task, do not fix.
- Total test coverage: 128 tests pass across `test_session_snapshot.py` (72 tests) and `test_session_merge.py` (56 tests).

## [2026-03-08] Task 5 - Truth bundle parsed-artifact validation
- Added shared parser module runtime/artifact_parsers.py so proof-gate and claim-judge consume one content-validation path for JUnit, SARIF, coverage, browser trace, and diff hunks.
- Proof gate now validates dict artifacts by kind+path with parser-backed blockers (proof_gate_artifact_file_missing_<kind> / proof_gate_artifact_parse_failed_<kind>), while preserving token checks for legacy string artifact refs.
- Claim judge now parses v2 artifact records via parse_artifact_content() and emits blocking reasons (artifact_parse_failed_<kind>) without changing test-intent-lock semantics.
- Artifact hash validation is wired in proof-gate as opt-in strictness: only 64-hex sha256 values are verified against file bytes to avoid breaking legacy placeholder hashes.

## [2026-03-08] Task 7 - Optional Semgrep CE integration
- Added run_semgrep_scan(project_dir, rules="auto") in runtime/security_check.py with graceful fallback. Missing semgrep, subprocess failures, malformed JSON, or unsupported return codes return {"status":"unavailable","findings":[],"error":"semgrep not found"} without crashing.
- Semgrep findings are normalized in two stages: run_semgrep_scan shape (severity, rule, path, line, message) and canonical conversion via _scan_semgrep() + _finding(...) with source semgrep-ce.
- tools/python_sandbox.py module docstring now explicitly states REPL-only scope; broader sandbox policy remains hook-mediated through hooks/firewall.py and hooks/secret-guard.py.
- Added tests for semgrep unavailable/available/malformed paths in tests/runtime/test_security_check.py, semgrep-unavailable no-crash coverage in tests/security/test_repl_sandbox.py, and REPL-only docstring coverage in tests/tools/test_python_sandbox.py.

## [2026-03-08] Task 6 - KEV and EPSS enrichment for dependency findings
- Added enrich_with_kev() and enrich_with_epss() in plugins/dephealth/cve_scanner.py following exact same 24h cache + offline/disabled fallback pattern as scan_for_cves.
- KEV cache: single JSON at .omg/state/kev-cache.json storing cve_ids array and fetched_at timestamp. EPSS cache: .omg/state/epss-cache.json with per-CVE entries dict, each having epss float and fetched_at timestamp.
- vuln_analyzer.py analyze_reachability() now calls both enrichers and adds kev_listed (bool) and epss_score (float|None) to its return dict.
- security_check.py already had kev_listed/epss_score in the dependency finding schema and unresolved_risks from Task 7 commit (8415397); our changes were idempotent there.
- 14 new tests in tests/plugins/test_dephealth.py covering: KEV match/miss, EPSS float score, offline degradation, stale cache fallback, fresh cache TTL, disabled mode defaults, empty CVE ID, vuln_analyzer integration.
- Commit: cc06382

## [2026-03-07] Task 8 - Background Verification State Pipeline
- Created runtime/background_verification.py with publish_verification_state() and read_verification_state(). Writes .omg/state/background-verification.json with schema BackgroundVerificationState, schema_version 2.
- proof_chain.py assemble_proof_chain() now calls publish_verification_state() after chain assembly in a try/except — fire-and-forget, never blocks proof chain return.
- tracebank.py record_trace() checks metadata.verification_status and, when present, publishes state using metadata.verification_blockers, verification_evidence_links, verification_progress.
- Added background-verification.json to MIGRATION_MAP in hooks/state_migration.py.
- 7 new tests in tests/runtime/test_background_verification.py: happy path, status variants, overwrite, directory creation, missing state degradation, corrupt file degradation, schema_version assertion.
- 29 tests pass across proof_chain/tracebank/hud/state_migration/background_verification.
- Commit: 5b8af56

## [2026-03-08] Task 9 — HUD Background Verification State

- `readBackgroundVerificationState(stateDir)` follows same `readJsonSafe` pattern as other state readers
- `renderVerificationStatus(state)` returns a string always (dim fallback for null state) — no conditional push needed
- `.sisyphus/` is gitignored — evidence files need `git add -f`
- HUD `safeMode` strips ANSI but preserves Unicode symbols (✓, ⟳, ✗)
- Verification section renders after background tasks, before model name in the `els[]` array
- Commit: `fb1c356` on `release/v2.0.8`

## [2026-03-08] Task 11 - Canonical mode-profile contract
- Added `load_canonical_mode_profile(mode)` in `runtime/runtime_profile.py` with explicit behavioral deltas: `chill` (1, quiet, minimal), `focused` (2, standard), `exploratory` (4, verbose, background verification on).
- Added `get_mode_profile(mode)` in `runtime/adoption.py` as the cross-surface delegation point to runtime canonical mode semantics.
- `hooks/setup_wizard.py` now exposes canonical setup mode selection helpers (`get_mode_choices`, `select_setup_mode`) and returns `setup_mode` payload with selected mode profile; default is `focused`.
- `hud/omg-hud.mjs` now reads `.omg/state/mode.json` and renders `mode:<name>` in the status line, keeping existing active mode badges behavior intact.
- Added TDD coverage for runtime profile contract, setup wizard canonical choices/default, and HUD mode display; targeted selector passed at `171 passed`.
## Task 10: Rollback UX Improvements
- Added `--status` command to `session_snapshot.py` to report current branch and snapshot count.
- Updated `main()` in `session_snapshot.py` to respect `OMG_STATE_DIR` environment variable, facilitating easier testing with mock directories.
- Tightened documentation in `session-branch.md`, `session-fork.md`, and `session-merge.md` with explicit scope statements and consistent command examples.
- Reinforced that rollback is limited to `.omg/state/` and does not affect git history or repo files.


## [2026-03-08] Task 13 - Gemini/Kimi canonical host schema foundation
- Expanded canonical host enum in `registry/omg-capability.schema.json` to include `gemini` and `kimi`, and added explicit `policy_model.host_rules` schema blocks for both hosts requiring `compilation_targets`, `mcp`, `skills`, and `automations`.
- Updated `runtime/contract_compiler.py` `SUPPORTED_HOSTS` to include `gemini`/`kimi` and made policy-model validation host-aware: Gemini/Kimi host rules are validated when declared, without requiring Claude/Codex-only `hooks` semantics.
- Added provider-level `HOST_RULES` constants to `runtime/providers/gemini_provider.py` and `runtime/providers/kimi_provider.py` documenting canonical capability contracts aligned to MCP config-writer support.
- Updated `OMG_COMPAT_CONTRACT.md` canonical host contract text/front matter so all four hosts are canonical, with Claude/Codex hook contracts distinct from Gemini/Kimi MCP-centric contracts.
- Added regression tests in `tests/runtime/test_contract_compiler.py` and `tests/test_public_surface.py` to enforce acceptance of Gemini/Kimi host declarations and rejection of incomplete Gemini host rules.
