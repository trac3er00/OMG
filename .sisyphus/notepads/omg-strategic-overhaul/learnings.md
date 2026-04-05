# Learnings — omg-strategic-overhaul

## Session Started: 2026-04-05

## Architecture Facts (verified)
- `hooks/state_migration.py` — migration infrastructure (NOT runtime/)
- `src/security/audit-trail.ts` + `src/security/audit-trail.test.ts` — audit trail (NOT src/audit/)
- `runtime/runtime_contracts.py:9-108` — canonical state modules source of truth
- XOR fallback lives in `runtime/memory_store.py:1048`
- Ralph loop hardcoded 50 iterations in `hooks/stop_dispatcher.py:1076`
- Context pressure demotes planning gate at `hooks/stop_dispatcher.py:1167`
- Entropy detection EXISTS in `hooks/_post_write.py` (Shannon entropy 4.5)
- Evidence retention EXISTS in `src/evidence/retention.ts` (8 policies, 7-365 days)
- 56 hook files in hooks/
- 25 agent skill packs in .agents/skills/omg/
- 118 runtime modules in runtime/
- Test infrastructure: 281 Python tests + 100+ TS tests

## Patterns to Follow
- Fail-closed: `setup_crash_handler("name", fail_closed=True)` (see hooks/firewall.py:26)
- Feature flag: `get_feature_flag("feature_name")` (see hooks/stop_dispatcher.py:1032)
- Atomic write: `atomic_json_write(path, data)` (see hooks/_common.py)
- State schema: always increment version field when changing format
- Evidence path: `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`

## [T3] Schema Audit
- Canonical state modules are still directory-based in `runtime/runtime_contracts.py`; the TS mirror flattens some of them, but the on-disk layout currently exposes `context_engine_packet.json`, `defense_state/current.json`, and `session_health/{default,latest}.json`.
- Schema-versioned on-disk payloads found: `session_health/default.json` and `session_health/latest.json` at `1.0.0`. `context_engine_packet.json` uses `packet_version=v2`; `defense_state/current.json` and `ralph-loop.json` have no schema_version.
- Wave 2 bump candidates: `ralph-loop.json`, `memory.sqlite3`, and ledger/audit artifacts (including `tool-ledger.jsonl`) because planned T8/T9/T10-T16 changes alter persisted shapes.
- Atomic write audit: `hooks/_common.py::atomic_json_write()` exists and is used widely, but several runtime state writers still use bespoke temp-file + replace code instead of the shared helper.
- Pytest note: `python3 -m pytest tests/ -k "schema" -v` failed during collection outside schema tests; schema tests that executed passed.

## Guardrails
- NEVER rename hook files (host-referenced in hooks/universal/hooks.json)
- NEVER break safe preset
- NEVER modify both Python hooks AND TS modules for same feature in same task
- Tool count must stay ≤45 per session
- Feature flags default to false until integration tests pass


## [T2] Feature Flag Audit
- Canonical pattern: `get_feature_flag("FLAG_NAME", default=...)` in hooks/_common.py; env var override uses `OMG_{FLAG}_ENABLED`.
- Existing flags audited across hooks/ and runtime/: 39 unique flags; defaults preserved exactly as found in code.
- Registry written to `.omg/state/feature-flags.json` with current flags plus Wave 2+ slots reserved false by default.
- No hook files were modified; audit found no new gating changes to apply.
- Notes: `hooks/post-tool-failure.py` imports the helper but does not invoke it.

## [T7] Security Posture Audit
- Critical bypass chain confirmed: `hooks/firewall.py` and `hooks/secret-guard.py` suppress all non-`deny` decisions under `is_bypass_mode()`, so ASK-class controls degrade to implicit allow in `dontAsk/bypassPermissions` mode.
- Settings governance bypass exists in `hooks/config-guard.py`: trust review is skipped in bypass/bypassall and the hook is fail-open on crash (`setup_crash_handler(..., fail_closed=False)`).
- `hooks/policy_engine.py` has an ASK-only branch for grep on secret-like paths; combined with firewall bypass suppression this yields a practical secret-inspection bypass path.
- Detection coverage gaps: `runtime/security_check.py` secret signatures are narrow (missing many modern token families), and absolute scope paths are not confined to project root.
- Hardcoded security thresholds are widespread and static (`runtime/defense_state.py` cutoffs, `_post_write.py` entropy 4.5/21, `runtime/security_check.py` size/time limits), reducing environment-specific tuning and incident responsiveness.
- Evidence artifact saved to `.sisyphus/evidence/task-7-security-audit.json` with structured findings, bypass path inventory, and threshold inventory.

## [T4] Tool Audit
- Repo-declared + hook-injected tool surface is **32 unique tools** (under the 45-tool degradation threshold), with high duplication pressure from repeated bundle declarations (96 raw `allowed_tools` entries collapse to 6 unique runtime tools).
- MCP inventory: `runtime/omg_mcp_server.py` exposes 10 `omg_*` tools; `runtime/mcp_memory_server.py` exposes 8 `memory_*` tools. Tool fabric lanes are registered from `control_plane/service.py` as exactly 4 lanes: `lsp-pack`, `hash-edit`, `ast-pack`, `terminal-lane`.
- Description quality is weak overall: many tool entries are schema/name-only (score 1-2), especially hook-injected read-only names and generic bundle tool declarations without examples or context.
- Highest-value consolidation candidates: merge `omg_policy_evaluate` + `omg_tool_fabric_request`, merge `memory_import` + `memory_import_bundle`, collapse `Bash*` variants into one `Bash` with policy constraints, and remove `LS` alias.
- Phase-gating strategy to preserve model performance: planning lane exposes mostly discovery/read tools, execution lane adds mutation + governance dispatch, verification lane narrows to evidence/judge/security checks; each phase can be held to <15 active tools.
- Full structured audit saved at `.sisyphus/evidence/task-4-tool-audit.json`.


## [T6] Skills Quality Audit
- Audited all 25 `SKILL.md` files under `.agents/skills/omg/` plus all 25 `registry/bundles/*.yaml` manifests and `runtime/skill_registry.py`.
- Systemic issue: SKILL prompts are largely schema-only metadata stubs (low procedural clarity, no explicit tool-failure handling, minimal edge-case coverage, no acceptance criteria beyond artifact path).
- Highest-priority rewrite targets: `terminal-lane`, `hash-edit`, `ast-pack`, `proof-gate`, `security-check`, `secure-worktree-pipeline`, `remote-supervisor`, `preflight`, `hook-governor`, `claim-judge`.
- Bundle manifest gaps: host-level tool policy mismatch in `control-plane` and `plan-council` (hosts list gemini/kimi but `allowed_tools` only defines claude/codex).
- Runtime linkage finding: `runtime/skill_registry.py:_summary_snippet` derives metadata from skill slug instead of SKILL content; prompt improvements currently do not influence compact registry summaries.
- Evidence saved: `.sisyphus/evidence/task-6-skills-audit.json` (contains full per-skill scoring, top-10 concrete rewrites, and per-bundle tool description quality matrix).

## [T5] Hooks Quality Audit
- Audited **all 56 Python hooks** under `hooks/` plus compiled ordering in `registry/bundles/hook-governor.yaml`; baseline `tests/hooks` currently reports pre-existing failures (`16 failed, 904 passed`) and was treated as non-regression context.
- Highest-risk quality concentration is in large control hooks: `stop_dispatcher.py` (1363 LOC), `setup_wizard.py` (1101), `prompt-enhancer.py` (1030), `_common.py` (1018), and `policy_engine.py` (775).
- Security fail-closed snapshot: `firewall.py` and `secret-guard.py` are correctly `fail_closed=True`; `terms-guard.py` is also fail-closed. `security_validators.py` is a utility module without hook crash-handler wiring (documented as compliance gap to clarify in policy docs).
- Top concrete fixes prioritized: `universal/start.py` runtime bug (`os.time()`), `stop_dispatcher.py` brittle YAML parsing, `policy_engine.py` hot-path regex precompilation, `pre-compact.py` file-handle hygiene, `secret-guard.py` allowlist audit fidelity, and `prompt-enhancer.py` structural refactor into staged pipeline functions.
- Performance concerns repeated across hooks: large stop-hook ledger scans, repeated state reads in hot paths, dense regex sweeps in policy routing, and optional network/subprocess hooks that should be more tightly guarded by platform/feature checks.
- Full machine-readable artifact written to `.sisyphus/evidence/task-5-hooks-audit.json` (includes per-hook score/issues/priority + top-10 exact fix proposals).

## [T1] Migration Tooling
- Implemented `src/config/migration.ts` as a v2.3.0→v3.0.0 migration engine with dry-run/apply modes and deterministic JSON report shape: `files_affected`, `changes_required`, `rollback_path`, `errors`.
- Embedded canonical state module/schema inventory directly from `runtime/runtime_contracts.py:9-108` to keep migration output aligned with Python contracts.
- Dry-run mode is non-mutating by design; apply mode creates rollback backups under `.omg/backups/migrations/<from>-to-<to>-<timestamp>` before atomic writes.
- Added CLI surface `omg migrate --from --to --dry-run|--apply` and validated `npx omg migrate --from=2.3.0 --to=3.0.0 --dry-run` emits JSON with exit code 0.

## [T8] XOR Elimination
- `runtime/memory_store.py` now imports `Fernet`/`InvalidToken` at module load as a hard dependency (no try/except module fallback path remains).
- Active encryption/decryption is Fernet-only; legacy deterministic ciphertext is accepted only inside migration handling and is re-encrypted to Fernet on first successful read.
- Added hardening tests for unreachable XOR fallback behavior, Fernet-only writes, legacy-to-Fernet migration, and import-time failure when `cryptography` is unavailable.

## [T9] HMAC Persistence
- Ephemeral HMAC key in `audit-trail.ts` was generated via `randomBytes(32)` on every instantiation — signatures unverifiable after process restart.
- Key now persisted to `.omg/state/audit-hmac.key` (hex-encoded 32 bytes, 64 chars). Loaded on startup, created if missing.
- File written with mode 0600 + explicit `chmodSync` to defend against permissive umask.
- Priority chain: `options.secret` > `OMG_AUDIT_HMAC_SECRET` env var > persisted key file.
- `AuditTrail.rotateKey()` static method: renames old key with `.{timestamp}.bak` suffix, generates fresh key.
- `StateResolver.stateDir` provides the canonical `.omg/state/` path — no need to reconstruct it manually.
- `atomicWrite` from `atomic-io.ts` was considered but `writeFileSync` with mode + `chmodSync` is simpler for a single small key file.

## [T14] Concurrent Locking

- Ralph session lock: `.omg/state/ralph-loop.lock` with PID-based ownership
- Stale lock detection via `os.kill(pid, 0)` — OSError/ProcessLookupError means dead
- `atomic_json_write` from `_common.py` used for lock file writes (symlink-safe, fsync'd)
- Lock acquired in `check_ralph_loop` when `active=true`, released on deactivation (timeout/max_iter)
- `_locked_path` context manager in `_common.py` is for short-lived file locks; session locks need PID-based approach
- Test pattern: subprocess tests use `CLAUDE_PROJECT_DIR` env var to point at tmp_path
- Dead PID 2147483647 (max int32) reliably doesn't exist for stale lock tests
- Iteration check: `iteration >= max_iter` uses pre-increment value, so test needs iteration=max to trigger

## [T10] Convergence Detection
- Ralph convergence can be implemented safely in `check_ralph_loop` by persisting per-iteration metrics (`last_delta_metrics`, `last_delta_score`, `no_delta_streak`) directly in `.omg/state/ralph-loop.json`.
- Meaningful-delta computation is stable when using: changed file count (`git diff --name-only HEAD`), tracked tool invocation count (`Bash`/`Write`/`Edit`/`MultiEdit`), and trailing test-result signature from tool-ledger bash test commands.
- Convergence gating should remain behind `get_feature_flag("ralph_convergence_detection", default=False)` so default behavior is unchanged unless explicitly enabled.
- `max_iterations` override should be loaded from `resolve_state_file(project_dir, "state/ralph-config.json", "ralph-config.json")` each loop iteration to allow runtime tuning without prompt-enhancer changes.
- Stop reasons are easiest to keep consistent via a single stop helper that deactivates state, writes `stop_reason`, and releases the Ralph lock (`completed`, `converged_no_delta`, `max_iterations`, `timeout`, `user_stop`).

## [T12] Approval Gate
- Ralph loop now hard-refuses bypass permission mode before iteration progression: `is_bypass_mode(data)` raises runtime error with explicit disable guidance.
- Added `ralph_approval_gate` enforcement path in `check_ralph_loop()` that inspects current turn tool results for destructive actions (delete commands, protected-path mutations, config overwrites).
- Approval resolution order: pre-approval file (`.omg/state/ralph-approvals.json`) → CLI prompt when interactive → auto-deny when non-interactive.
- Every destructive-action decision is audit-trailed to `.omg/state/ledger/ralph-approval-audit.jsonl` with mode (`preapproved`/`cli_prompt`/`auto_deny`) and action metadata.
- Regression coverage added for bypass refusal, gate firing on destructive action, and pre-approval honoring.


## [T11] Rollback Manifests
- Wired `runtime.rollback_manifest` into Ralph loop via `create_rollback_manifest`, `classify_side_effect`, and `record_side_effect` so iteration manifests carry rollback-aware side-effect metadata without rewriting runtime schema code.
- Added per-iteration capture in `check_ralph_loop`: snapshot diffing + ledger delta extraction, then persisted `.omg/state/ralph-rollbacks/iteration-{N}.json` with `{iteration, files_changed, side_effects, rollback_commands}`.
- Snapshot strategy uses git file inventory + SHA-256 hashes to classify `created/modified/deleted`; rollback commands are generated as `git checkout -- <path>` for tracked files and `rm -f <path>` for untracked creates.
- Side-effect taxonomy emitted for Ralph manifests: `file_created`, `file_modified`, `file_deleted`, `config_changed`, `command_executed`; command/config effects are inferred from new tool-ledger entries per iteration.
- Validation: `python3 -m pytest tests/test_stop_dispatcher.py -v` passed (40 passed), with new tests covering manifest creation, schema fields, and executable rollback restoration for tracked files.
