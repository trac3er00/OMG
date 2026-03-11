# Learnings

## [2026-03-11] Session start
- Main worktree: /Users/cminseo/Documents/scripts/Shell/OMG
- Baseline test run: `python3 -m pytest tests/test_prompt_enhancer.py tests/runtime/test_tool_plan_gate.py -q` => 25 passed in 6.35s
- pyproject.toml line 89 has pytest/xdist/timeout/coverage defaults
- Python test runner: python3 -m pytest
- 16 tasks + 4 Final Wave tasks
- Wave 1 (tasks 1-6): governance foundations
- Wave 2 (tasks 7-11): runtime hardening + storage
- Wave 3 (tasks 12-16): Forge, setup, evidence, docs

## [2026-03-11] Task 2 complexity scorer
- Added `runtime/complexity_scorer.py` as a shared complexity SSOT returning `{score, category, governance}`.
- Preserved Task 1 pinned labels for non-empty goals (`<10` words low, `10-24` medium, `>=25` high) while still supporting a score bucket path for empty goals (`trivial`).
- Governance payload now includes booleans (`read_first`, `simplify_only`, `optimize_only`) and mirrored labels (`complexity`, `complexity_score`) with no trust/defense/eval-gate blending.
- `runtime/tool_plan_gate.py` now delegates complexity labeling to shared scorer and maps `trivial` to `low` for existing budget-estimate compatibility.
- `hooks/prompt-enhancer.py` keeps its existing heuristic trigger score but imports and calls shared `score_complexity` for categorical labeling.
- Validation: `python3 -m pytest tests/runtime/test_tool_plan_gate.py -q -k complexity` (10 passed) and `python3 -m pytest tests/test_prompt_enhancer.py tests/runtime/test_tool_plan_gate.py -q` (48 passed).

## [2026-03-11] Task 6 test-intent-lock cwd decoupling
- Fixed two cwd-coupled bugs in `runtime/test_intent_lock.py`:
  1. Line 309: `_load_lock_payload(lock_id)` used `Path(".omg")` (cwd-relative)
  2. Line 378: `_evaluate_locked_contract` called `_hash_test_file(Path("."), path_key)` (cwd-relative)
- Solution: Added optional `project_dir: str | None = None` parameter to `evaluate_test_delta()` and `_evaluate_locked_contract()`
- When `project_dir` is provided, uses `_load_lock_payload_from_project(project_dir, lock_id)` (already existed at line 320-322)
- When `project_dir` is None, falls back to cwd-relative behavior for backward compatibility
- Added two regression tests: `test_evaluate_test_delta_off_cwd_with_project_dir` and `test_evaluate_test_delta_off_cwd_catches_cwd_regression`
- Validation: `python3 -m pytest tests/runtime/test_test_intent_lock.py -q` => 18 passed (16 existing + 2 new)
- Commit: `fix(test-intent): remove cwd-coupled lock resolution`

## [2026-03-11] Task 3 advisory governance emission
- Added `@governance:` line to DISCIPLINE section of prompt-enhancer.py (lines 309-325)
- Key bug: `score_complexity` import at line 22-25 was unreachable in subprocess context — `sys.path` only contained hooks/ dir, not project root. Fixed by moving import after sys.path setup and adding `_PROJECT_ROOT` to path.
- Governance emits `read_first`, `simplify_only`, `optimize_only`, `complexity` fields from `score_complexity()` for fix/implement/refactor/plan/review intents only.
- Zero-injection fast path (lines 145-146) completely untouched — "hello" still produces empty output.
- 3 new tests in TestAdvisoryGovernance class; 32 total tests pass.
- Learning: Hook scripts running as subprocesses have `sys.path[0]` = script directory, NOT project root. Any `from runtime.*` import needs explicit project root path injection.

## [2026-03-11] Task 4 context/tool-plan governance propagation
- `runtime/tool_plan_gate.py` now carries advisory governance in plan payload as `governance_payload` using `score_complexity(normalized_goal)["governance"]` with crash-safe fallback `{}`.
- `runtime/context_engine.py` packet now includes `governance` and keeps fallback as `{}` for runs without governance state.
- Added `_compose_governance(raw)` to pull optional `intent_gate.governance` without changing compliance authority.
- Compliance precedence remains unchanged: clarification and council verdicts still outrank advisory governance hints.
- Added regression coverage: `test_build_tool_plan_includes_governance_payload` and packet governance key/default assertions.
- Validation: `python3 -m pytest tests/runtime/test_tool_plan_gate.py tests/runtime/test_context_engine.py -q` => 41 passed.

## [2026-03-11] Task 5 mutation gate hardening
- Added `_write_warning_artifact()` to `runtime/mutation_gate.py` — mirrors `_write_block_artifact` with `"status": "warning"` and `warn-{hash}.json` filename.
- Permissive-allow path now persists evidence to `.omg/state/mutation_gate/` alongside the existing `warnings.warn`.
- Restricted `metadata.exempt` bypass: `metadata.exempt=True` alone no longer grants instant exemption. Requires `normalized_exemption in _EXEMPTIONS` OR `metadata_obj.get("exempt_reason")`.
- Updated `test_mutation_gate_allows_explicit_exempt_metadata` to include `exempt_reason` in metadata.
- Added 3 new tests in `test_tdd_gate.py`: `test_mutation_gate_demotes_exempt_without_reason`, `test_mutation_gate_exempt_with_exemption_category`, `test_mutation_gate_writes_warning_artifact`.
- Added 2 new tests in `test_server_v2.py`: `test_mutation_gate_endpoint_v2_allows_no_lock`, `test_mutation_gate_endpoint_v2_blocks_strict_mode`.
- xdist gotcha: HTTP server tests that depend on env vars need `monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)` to avoid leakage from parallel workers.
- Validation: `python3 -m pytest tests/control_plane/test_server_v2.py tests/hooks/test_tdd_gate.py -q` => 22 passed (was 17).

## [2026-03-11] Task 7 hook-sprawl governance awareness tests
- Added two new tests to `tests/runtime/test_hook_governor.py`:
  1. `test_hook_inventory_fully_classified()` — verifies all 53 Python files in hooks/ are classified
  2. `test_hook_inventory_catches_unclassified()` — negative test ensuring unclassified files are caught
- Classification strategy: 3 categories:
  * Registered hooks (14 files in settings.json): firewall.py, secret-guard.py, tdd-gate.py, etc.
  * Internal helpers (11 files with _ prefix): _common.py, _budget.py, _memory.py, etc.
  * Dormant/unregistered hooks (28 files): legitimate but not in settings.json (branch_manager.py, policy_engine.py, etc.)
- Test extracts registered hooks by parsing settings.json hook commands (e.g., "python3 $HOME/.claude/hooks/firewall.py")
- Allowlist is NOT brittle: new legitimate helpers can be added without changing file count
- Prevents hook-sprawl by enforcing explicit classification — test FAILS if unclassified file is added
- Validation: `python3 -m pytest tests/runtime/test_hook_governor.py -q` => 10 passed (8 existing + 2 new)
- Commit: `test(hooks): enforce hook inventory governance`

## [2026-03-11] Task 9 blind-spot suite
- Added 34 new tests across 3 files (14 subagent dispatcher, 14 MCP store, 6 hook injection).
- `_run_configured_worker` has good error-path coverage: TimeoutExpired, OSError, empty command, malformed template, and nonzero exit all return structured error dicts.
- `_run_job` mid-execution cancellation is race-safe: the post-dispatch lock check at line 401 catches `status == "cancelled"` and returns without overwriting to "completed".
- `_run_job` worktree cleanup happens in `finally` block — confirmed cleanup occurs even when dispatch raises.
- `MemoryStore` JSON backend tolerates corrupted files, non-list JSON, and empty files — all return empty store.
- `MemoryStore.search()` is resilient to items with missing `key` field, `None` tags, or non-list tags — search still works on `content` field.
- Pre-existing 7 MCP test failures are caused by `mcp_module` fixture setting `store.store_path` to a `.json` path AFTER init, but `_backend` stays `"sqlite"` — `_items` manipulation has no effect on sqlite backend's `count()`.
- Firewall hook (`hooks/firewall.py`) handles malformed JSON, empty stdin, and missing `tool_name` gracefully — all exit code 0.
- Firewall hook survives corrupted defense_state and council_verdicts JSON — still produces `ask` decision for network commands.
- `score_complexity()` returns `dict[str, object]` which causes LSP `__getitem__` errors on `governance` dict access — workaround: `assert isinstance(gov, dict)` before key access.
- Validation: 812 passed, 8 failed (all pre-existing)
- Commit: `test(runtime): cover subagent and MCP blind spots`

## [2026-03-11] Task 12 modular Forge reality layer
- Added intent-aware operation classification in `runtime/forge_agents.py` via `classify_operation_intent(job)` with structured-key precedence (`operation`, `intent`, `change_type`, `action`) and prompt-text fallback.
- Added bounded operation plan resolution (`resolve_operation_plan`) backed by contract-defined orchestration profiles rather than freeform planning.
- Dispatch now propagates `operation_plan` into result payload, specialist dispatch evidence, and adapter evidence orchestration metadata while preserving existing domain/specialist validation gates.
- Added `operation_orchestration` profiles to `runtime/forge_contracts.py` (`add`, `edit`, `delete`, `unknown`) to keep orchestration modular and contract-governed.
- TDD flow: added failing tests first in `tests/runtime/test_forge_agents.py`, confirmed import failure, then implemented and validated with `python3 -m pytest tests/runtime/test_forge_agents.py -q` (40 passed).

## [2026-03-11] Task 10 memory contracts
- Added host-qualified namespace contract (<host>:<namespace>) to memory add/search/list/import paths while keeping existing interfaces backward compatible via optional params.
- Added retention metadata (retention_days, computed expires_at) and consistent expiry filtering for list/search/export operations.
- Added inline PII redaction before persistence for email, US phone, and SSN patterns in both store and import flows.
- Added isolated MCP tests that replace module _store with tmp_path JSON backend to avoid shared sqlite-state failures.
