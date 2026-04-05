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
- If a Ralph state is already inactive but carries `completed`/`user_stop` markers, backfilling `stop_reason` on read keeps downstream state consumers deterministic without reactivating the loop.

## [T12] Approval Gate
- Ralph loop now hard-refuses bypass permission mode before iteration progression: `is_bypass_mode(data)` raises runtime error with explicit disable guidance.
- Added `ralph_approval_gate` enforcement path in `check_ralph_loop()` that inspects current turn tool results for destructive actions (delete commands, protected-path mutations, config overwrites).
- Approval resolution order: pre-approval file (`.omg/state/ralph-approvals.json`) → CLI prompt when interactive → auto-deny when non-interactive.
- Every destructive-action decision is audit-trailed to `.omg/state/ledger/ralph-approval-audit.jsonl` with mode (`preapproved`/`cli_prompt`/`auto_deny`) and action metadata.
- Regression coverage added for bypass refusal, gate firing on destructive action, and pre-approval honoring.

## [T18] Multi-Model Routing
- `runtime/router_selector.py::select_target()` now supports feature-gated (`get_feature_flag("multi_model_routing")`) complexity-aware model tiering while preserving legacy target routing when disabled.
- Complexity is sourced from `runtime.complexity_scorer.score_complexity()` and mapped to configurable tiers (`light|balanced|heavy`) with family coverage for Claude, GPT-5.4, and Kimi.
- Budget pressure rule is deterministic: when remaining budget ratio is below 20%, routing downgrades one tier to reduce cost; latency-sensitive context also downgrades one tier toward faster models.
- Added targeted regression tests in `tests/runtime/test_router.py` covering simple-task light routing, high-complexity heavy routing, and low-budget downgrade behavior.


## [T11] Rollback Manifests
- Wired `runtime.rollback_manifest` into Ralph loop via `create_rollback_manifest`, `classify_side_effect`, and `record_side_effect` so iteration manifests carry rollback-aware side-effect metadata without rewriting runtime schema code.
- Added per-iteration capture in `check_ralph_loop`: snapshot diffing + ledger delta extraction, then persisted `.omg/state/ralph-rollbacks/iteration-{N}.json` with `{iteration, files_changed, side_effects, rollback_commands}`.
- Snapshot strategy uses git file inventory + SHA-256 hashes to classify `created/modified/deleted`; rollback commands are generated as `git checkout -- <path>` for tracked files and `rm -f <path>` for untracked creates.
- Side-effect taxonomy emitted for Ralph manifests: `file_created`, `file_modified`, `file_deleted`, `config_changed`, `command_executed`; command/config effects are inferred from new tool-ledger entries per iteration.
- Validation: `python3 -m pytest tests/test_stop_dispatcher.py -v` passed (40 passed), with new tests covering manifest creation, schema fields, and executable rollback restoration for tracked files.

## [T15] Plan Adherence
- Planning gate demotion under high context pressure was removed from `check_planning_gate`; pending checklist items now remain blocking regardless of pressure state.
- Added `plan_adherence_check(project_dir, data)` and wired it into `check_ralph_loop` so each Ralph iteration can fail-closed on actions that drift outside the active plan when `plan_adherence_enforcement` is enabled.
- Added session segmentation checkpoints in Ralph loop under high context pressure with bounded phases and mandatory checkpoint blocks.
- Segmentation tuning is config-driven via `ralph-config.json` keys: `session_segmentation_threshold_tokens` and `session_segmentation_phase_iterations`.
- `plan_adherence_enforcement` remains default-false (already present in `.omg/state/feature-flags.json`), keeping behavior opt-in until explicitly enabled.
- Verification: `python3 -m pytest tests/test_stop_dispatcher.py -v` → `43 passed`.

## [T13] Fernet Migration
- T8's on-read migration path (`_decrypt_text` with `migrate_item_id`) works correctly: Fernet `InvalidToken` → try XOR `_try_decrypt_legacy_payload` → re-encrypt with Fernet → commit.
- Added `migrate_all(batch_size, dry_run)` to `MemoryStore` for bulk migration with batched commits (default 100 rows/batch) to avoid long-held transactions on large DBs.
- Classification logic: entries starting with `enc:v1:` are tried with Fernet first (skip if valid), then XOR legacy; entries without prefix are plaintext (encrypt to Fernet); undecodable entries are logged and skipped.
- JSON backend migration is a no-op — content is stored plaintext in JSON files; only SQLite backend has encrypted content columns.
- CLI entry point: `python3 -m runtime.memory_migrate [--store-path] [--batch-size] [--dry-run] [--json]` — returns exit code 1 when corrupted entries exist.
- MCP tool: `memory_migrate(dry_run, batch_size)` added to `runtime/mcp_memory_server.py` for agent-accessible migration.
- Edge case coverage: empty DB, already-Fernet, corrupted/undecryptable, batch commit boundaries, mixed DB, dry-run, JSON noop, unicode data integrity, CLI subprocess.
- All 50 tests pass (41 from T8 + 9 new migration tests).

## [T19] SIEM Export

- AuditTrail stores entries as JSONL at `{stateDir}/ledger/audit.jsonl` with HMAC signatures
- SIEM export maps AuditLogEntry → SiemEvent: timestamp, actor, action, resource, decision, risk_level, session_id, evidence_ref
- Resource/decision/risk_level extracted from `details` field with sensible fallbacks (action prefix, "recorded", "info")
- Enterprise tier gating via `OMG_TIER` env var or explicit `tier` option; throws `SiemChannelError` for non-enterprise
- CLI wired as `npx omg audit export --format=jsonl --output=<path>` using yargs nested subcommand
- `readJsonLines` from atomic-io.ts handles JSONL reading with graceful skip of malformed lines
- stdout export supported via `--output=-` pattern
- 10/10 tests pass (6 original + 4 new SIEM tests)

## [T17] Approval UI
- Created `hooks/approval_ui.py` as terminal-based governance gate approval UI, following existing `stop_dispatcher.py` patterns for interactive detection (`sys.stdin.isatty()`) and JSONL ledger writing.
- Resolution order: pre-approval file (`.omg/state/ralph-approvals.json`) → interactive TTY prompt → auto-deny when non-interactive. Matches T12 Ralph approval gate convention.
- `present_approval_request()` returns "approve"/"deny"/"approve_all"/"deny_all"; `_input_fn` kwarg enables test injection without monkeypatching stdin.
- Every decision logged to `.omg/state/ledger/approvals.jsonl` with SHA-256 integrity digest for tamper detection.
- Wired into `trust_review.py`: `review_config_change()` and `regenerate_trust_manifest()` gained `resolve_ask=` kwarg (default False for backward compat); when True + verdict=="ask", approval UI is presented.
- Pre-approval supports three modes: `allow_all`, `approved_risk_levels` (list), `approved_actions` (list of action strings).
- ANSI color respects `NO_COLOR`/`FORCE_COLOR` env vars per terminal color spec.
- 36 new tests (test_approval_ui.py) + 8 existing trust_review tests pass with no regression.

## [T22] Skill Self-Improvement
- Applied all top-10 T6 rewrites directly into the corresponding `SKILL.md` prompts, replacing schema-only stubs with executable procedures that include concrete `file:function` runtime references.
- Added explicit failure handling paths per skill (deny/abort/fail-closed/stop conditions) so high-risk lanes do not silently downgrade to advisory behavior.
- Upgraded each top-10 skill frontmatter description to substantive, non-misleading operator summaries (all lengths validated in the 50-300 char range).
- Updated matching bundle manifest descriptions (`registry/bundles/{terminal-lane,hash-edit,ast-pack,proof-gate,security-check,secure-worktree-pipeline,remote-supervisor,preflight,hook-governor,claim-judge}.yaml`) to align with the rewritten procedural semantics.
- Ran deterministic quality verification script: all top-10 skills passed description-length, error-guidance, file:function-reference, and bundle/skill reference integrity checks.
- Evidence artifact written to `.sisyphus/evidence/task-22-skill-quality.json` with `improved_skills` list and `quality_checks.all_pass=true`.

## [T16] Tool Consolidation
- Added descriptive `@mcp.tool(description=...)` text for all `omg_*` and `memory_*` tools in runtime MCP servers so tool metadata describes behavior and usage context rather than schema fields.
- Implemented phase exposure map in `runtime/tool_fabric.py` with aliases (`plan/execute/verify`) and explicit subsets for planning, execution, and verification phases.
- `ToolFabric.request_tool()` now honors optional `context["phase"]` and blocks requests for tools hidden in that phase, enabling lane-based exposure without changing lane registration count.
- Current tool inventory remains at 32 from T4 audit (<=45 threshold) while per-phase active sets stay compact (planning=10, execution=11, verification=9).

## [T20] Budget Tracking

- `runtime/budget_envelopes.py` provides `BudgetEnvelopeManager` with `create_envelope()`, `record_usage()`, `get_envelope_state()`, `get_envelope_pressure()` — fully functional multi-dimensional budget tracking
- Feature flag `ralph_budget_tracking` already existed in feature-flags.json with default: false
- Wired into `check_ralph_loop()` via `_ralph_budget_tracking()` — called between convergence detection and max_iterations check
- Budget envelope uses a per-session run_id stored in ralph state as `_budget_run_id` for isolation
- Ralph state gets three new fields: `budget_used`, `budget_remaining`, `budget_limit`
- Thresholds: 70% warn (advisory), 85% reflect (stronger advisory), 100% block (stop_reason="budget_exceeded")
- `tokens_per_iteration` and `budget_token_limit` are configurable via `ralph-config.json`
- Budget advisories flow through the `check_ralph_loop` return tuple as the advisories list element
- `_stop_ralph_loop` helper already handles state persistence + lock release — reused cleanly for budget stops

## [T21] Hook Self-Improvement
- Top-10 audit fixes are safest when treated as behavior-preserving micro-refactors: keep hook file names/signatures identical and target only brittle internals (timestamp API, parser, hot-path regex, handle hygiene, logging fidelity, platform gating, structured parsing).
- `stop_dispatcher._read_policy_flags` is more robust with `yaml.safe_load` + nested extraction fallback than line parsing; this prevents quoted/nested policy drift while preserving default mode fallback.
- `policy_engine` hot-path checks should use precompiled regex tuples and `.search()` methods to avoid repeated runtime compilation in per-command evaluation.
- For `secret-guard`, allowlist forensics quality depends on deriving `allowlisted` from policy decision reason (`Allowlisted:` prefix) and persisting that bit in audit logs.
- `fetch-rate-limits` should remain fail-open (`fail_closed=False`) but must avoid unnecessary keychain probing outside Darwin and run under crash-handler guard.
- Structured assistant content in `todo-state-tracker` needs normalization of list/dict blocks into plain text before TODO regex matching, otherwise cross-turn pending items can be dropped.
- Added 10 targeted tests (1 per improved hook) to pin these regressions; targeted suite passes even though the broader hooks suite still contains the known pre-existing 16 failing tests.

## [T23] Deep Planning
- Extended `runtime/opus_plan.py` with a governed deep planning pipeline that emits a structured plan payload (`id`, `version`, `objective`, `tasks`, `governance_checkpoints`, timestamps, routing metadata).
- Added per-task governance evaluation using `hooks.policy_engine.PolicyDecision` semantics (`allow|ask|deny`, risk level, controls) so each task carries a checkpoint before execution.
- Added persistence/versioning to `.omg/plans/{plan-id}.json` via `persist_governed_plan()`, including monotonic version increments and embedded history snapshots of prior versions.
- Added `diff_plans(plan_v1, plan_v2)` to compute added/removed/modified task deltas for version-to-version review.
- Integrated multi-model planning selection through `runtime.router_selector.select_target()` and retained tier-aware fallback routing.
- New tests in `tests/runtime/test_opus_plan.py` validate governed checkpoints, persistence+versioning, and plan diff computation.

## [T28] Evidence Retention

- `retention.ts` already had `applyRetentionPolicy` for file-level archive/delete; new prune layer adds gzip compression on top
- Evidence files: `.json`, `.jsonl`, `.txt` in `.omg/evidence/`; registry is JSONL at `.omg/state/ledger/evidence-registry.jsonl`
- `gzipSync`/`gunzipSync` from `node:zlib` — synchronous is fine for evidence files (small, local)
- CLI pattern: yargs nested subcommands with lazy `await import()` for each handler
- `exactOptionalPropertyTypes` in tsconfig requires explicit conditional property assignment (can't pass `undefined` for optional props)
- `readJsonLines` from `atomic-io.ts` returns empty array for missing files — safe for query on fresh projects
- Evidence types: security, test, build, governance, planning — matches the 5 categories from the evidence registry

## [T24] Multi-Agent
- `runtime/subagent_dispatcher.py` now stamps each submitted job with `governed_context` carrying a per-job tool fabric lane id (`subagent-lane-<job_id>`), budget envelope metadata, and rollback manifest path/step id.
- Governed context materialization is lazy but enforced at execution start via `_ensure_governed_context(...)`, which creates per-agent budget envelopes (`runtime.budget_envelopes`) and rollback manifests (`runtime.rollback_manifest`) before dispatch runs.
- Added shared `AgentCoordinator` ownership tracking (`file_path -> job_id`) and conflict gating in `_run_job`: when a second agent claims an already-owned file, policy decision (`allow|ask|deny`, default deny) is recorded and non-allow decisions fail the job.
- Dispatch artifacts/evidence now include `modified_files`, `governed_context`, `budget_check`, `file_ownership`, and `conflict_gate` so cross-agent governance decisions are auditable.
- Regression tests added in `tests/runtime/test_subagent_dispatcher.py`:
  - `test_multi_agent_governed_context`
  - `test_cross_agent_file_conflict_detected`
- Verification snapshot:
  - `python3 -m pytest tests/runtime/test_subagent_dispatcher.py -v` passed
  - `python3 -m pytest tests/runtime/ -k "agent" -v` still reports unrelated pre-existing collection errors in non-T24 modules (`agent_selector`, `router_selector`, coordinator-state shim, Python 3.11 `typing.override`).

## [T27] Cost Tracking

- T20's budget tracking uses flat `tokens_per_iter` estimate via `BudgetEnvelopeManager` — effective for token-based limits but lacks cost granularity
- Per-iteration cost records stored in `state["iterations"]` list; each record: `tokens_input`, `tokens_output`, `api_cost_usd`, `tool_invocations`, `wall_time_seconds`
- Token split uses configurable `input_output_ratio` (default 0.7 input / 0.3 output) — matches typical Claude conversation patterns
- Cost estimation uses `cost_per_1k_input_tokens` and `cost_per_1k_output_tokens` config keys — defaults to Claude Sonnet pricing ($3/M input, $15/M output)
- USD-based budget enforcement via `budget_cost_usd_limit` in ralph-config.json — complements existing token-based limit
- Completion report attached to state on Ralph stop via `state["completion_report"]` — includes total_cost, iteration count, per-iteration breakdown
- Wall time tracking uses `_last_iteration_ts` marker in state — first iteration gets 0.0 since no prior timestamp exists
- Tool invocations tracked via ledger entry mark (`_ledger_entry_mark`) — counts entries since last iteration
- Both existing budget tests (T20) pass unchanged — new fields are additive, existing assertions unaffected
- pyright type errors on `config.get()` → `float()` resolved with `str()` coercion wrapper

## [T26] Security Fixes

- Bypass-mode suppression is now policy-driven: firewall/secret-guard only auto-skip low-risk asks and hard-block `deny-on-bypass` or high-risk ask decisions.

## [T30] Orchestration Tests
- End-to-end orchestration coverage is stable when integration tests compose real runtime modules (`opus_plan`, `subagent_dispatcher`, `router_selector`, `tool_plan_gate`, `proof_gate`) and only stub external worker execution boundaries.
- `subagent_dispatcher` can be made deterministic in integration tests by monkeypatching `get_executor()` to an immediate executor; this preserves real submit/run status transitions while removing async flakiness.
- Cross-agent conflict detection is easiest to exercise by stubbing `_dispatch_job_task` to return identical `modified_files` for two different jobs and asserting `conflict_gate.status == fired` with deny policy.
- Plan adherence verification should assert both sides of the gate: mutation blocked without test-intent lock, then allowed with lock + done_when metadata under the same run-scoped tool plan.
- Budget/routing assertions are more robust when validating downgrade intent (`budget<20%` reason + not-heavy model tier) rather than pinning one exact tier for all complexity-scoring outcomes.
- Bash command enforcement now evaluates normalized command views (Unicode NFKC + empty-quote deobfuscation + shell tokenization), closing regex-evasion gaps like `c''url`.
- Secret-file grep/search against secret-like paths now returns `deny` (not `ask`), removing bypass-assisted secret inspection paths.
- Config governance moved to fail-closed behavior (`config-guard` crash/import/config-parse failures now block) and bypass mode no longer skips trust review for hooks/permissions/MCP/policy surfaces.
- `runtime/defense_state.py` thresholds are no longer hardcoded-only: defaults are overridable from `settings.json` (`_omg.defense_state.thresholds`) and `.omg/policy.yaml` (`defense_state.thresholds`) with persisted `threshold_source` in state artifacts.
- Added security regression coverage in `tests/security/test_security_posture_hardening.py` plus hook test updates for new deny-on-bypass semantics and config fail-closed behavior.

## [T34] Documentation
- v3.0.0 upgrade guide created at `docs/upgrade-v3.md` covering XOR removal, HMAC persistence, and security hardening.
- README comparison table updated to reflect v3.0.0 capabilities (Rollback, Multi-Model Routing, Deep Planning, Multi-Agent) against competitors.
- Migration path documented using `npx omg migrate` CLI.
- Feature flags for all new v3.0.0 capabilities are documented as default-off to preserve stability.

## [T33] Tool Descriptions
- Audited all MCP tool definitions exposed by `runtime/omg_mcp_server.py` (10 `omg_*` tools) and `runtime/mcp_memory_server.py` (9 `memory_*` tools), for a total of 19 tools.
- All 19 descriptions pass the quality gate: behavior-aligned (non-misleading), natural-language (not schema-only), 50-300 character length, and explicit usage context (`Use ...`/`Call this ...`).
- No source description edits were required in this pass (`fixed=0`), confirming T16 metadata improvements are holding.
- Evidence artifact written: `.sisyphus/evidence/task-33-tool-descriptions.json` with per-tool checks and aggregate counts.
- Overhaul-adjacent note: `memory_migrate` is in MCP scope and passes; `approval_ui`/`autorun` are not `@mcp.tool` entries in the audited server surfaces for this repository snapshot.

## [T32] Cross-Host Compile

- The `contract compile` CLI command was missing from `src/cli/index.ts`. The contract-compiler library existed at `src/runtime/contract-compiler/` but had no CLI entry point.
- Added `src/cli/commands/contract.ts` with `contract validate` and `contract compile --host <host>` subcommands, registered in the main CLI.
- The contract compiler uses a `ContractSchema` with version, capabilities, hosts, and tools. Validation checks: schema structure, required capabilities per host, and major version compatibility with `CANONICAL_VERSION`.
- All 4 canonical hosts (claude, codex, gemini, kimi) compile successfully with exit code 0.
- Host artifact targets: claude -> `.claude-plugin/mcp.json`, codex -> `.agents/skills/omg/`, gemini -> `settings.json`, kimi -> `mcp.json`.
- The `ship.ts` and `validate.ts` commands already had `runContractValidate()` that checked for `omg contract` in help text — previously always skipping. Now it will find and execute the command.
- Yargs `CommandModule` type with `readonly` interface fields + `array: true` option causes type mismatch; workaround is casting via `argv as unknown as Args` pattern.

## [T29] Integration Tests
- Added `tests/integration/test_security_automode_governance.py` with 10 cross-cutting scenarios that intentionally validate interactions between Ralph auto-mode flow, mutation gating, rollback manifests, governance approvals, security firewall behavior, planning gate enforcement, and lane-based tool exposure.
- Bun can execute `src/security/audit-trail.ts` directly from Python integration tests (`subprocess.run(["bun", "-e", ...])`), enabling restart/persisted-HMAC verification from the pytest lane without creating JS wrapper files.
- Ralph lock contention tests must use a different live PID than the test process; `_acquire_ralph_session_lock()` treats same-PID ownership as a valid re-entry and will not emit concurrency blocks.
- Current repo state has unrelated pre-existing integration failures in `tests/integration/test_cross_gap.py`; T29 module passes fully in isolation (`10 passed`).
