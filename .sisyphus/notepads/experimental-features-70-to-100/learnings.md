
## [2026-03-05] Task 1: Feature flag backward compat

- **Change**: Added _oal fallback to get_feature_flag() in hooks/_common.py (lines 220-222)
- **Pattern**: 
  ```python
  omg_features = settings.get("_omg", {}).get("features", {})
  oal_features = settings.get("_oal", {}).get("features", {})
  _FEATURE_CACHE.update(omg_features or oal_features)
  ```
- **Priority**: _omg takes precedence over _oal (via `or` operator)
- **Tests**: All 6 tests in test_common.py pass, including test_feature_flags
- **Evidence**: 
  - task-1-flag-omg-read.txt: _omg feature flag reading verified
  - task-1-flag-oal-fallback.txt: _oal fallback and priority verified
- **Commit**: fix(hooks): add _oal→_omg backward compat fallback to get_feature_flag

## [2026-03-05] Task 3: Test infrastructure created

- **Structure**: `tests/claude_experimental/` with conftest.py, test_package_init.py, 4 tier dirs
- **Fixtures** (in conftest.py):
  - `temp_db`: Temporary SQLite database with WAL mode
  - `feature_flag_enabled`: Factory to enable flags via env var (OMG_*_ENABLED=1)
  - `feature_flag_disabled`: Factory to disable flags via env var (OMG_*_ENABLED=0)
  - `mock_job_factory`: Create mock job dicts for lifecycle testing
- **Pytest marker**: `experimental` — use `@pytest.mark.experimental` on all new exp. tests
- **Tests created**: 11 smoke tests in test_package_init.py
  - TestPackageImports: 5 tests verifying all 4 tiers + root package import
  - TestFeatureFlagGating: 4 tests verifying disabled-by-default, env var toggle, version format
  - TestTierAvailabilityDict: 2 tests verifying tier_availability() structure and types
- **Verification**:
  - `pytest tests/claude_experimental/ -x -q` → 11 passed ✓
  - `pytest tests/claude_experimental/ -x -q -m experimental` → 11 passed ✓
  - `pytest tests/test_common.py -x -q` → 6 passed (existing unaffected) ✓
- **pytest.ini update**: Added `experimental` marker to markers list
- **Commit**: test(experimental): add test infrastructure with conftest fixtures and markers

## [2026-03-05] Task 4: Real subprocess dispatch in subagent dispatcher

- **Dispatcher shift**: Replaced simulated `_run_job()` artifact generation with real CLI dispatch via `_dispatch_to_cli()` in `runtime/subagent_dispatcher.py`
- **Agent context loading**: Added `_load_agent_definition(agent_name)` to read `agents/{agent}.md` and prepend it to the job prompt when available
- **Timeout behavior**: `_run_job()` now converts `subprocess.TimeoutExpired` into `TimeoutError` and marks job failed through existing lifecycle handling
- **Artifact schema**: Job artifacts now emit `type=agent_output` with `content`, `exit_code`, `duration_ms`, optional capped `stderr`, and `produced_at`
- **Fallback mode**: `_dispatch_to_cli()` tries `opencode run` first and returns an explicit no-CLI stub response when dispatch CLIs are unavailable
- **Parallel API surface**: Added `claude_experimental/parallel/executor.py` with `ParallelExecutor` (`submit`, `status`, `wait`, `cancel`, `submit_many`, `wait_all`) behind `PARALLEL_DISPATCH`
- **Test alignment**: Updated runtime dispatcher test expectation from legacy `result` artifact type to `agent_output` to match new runtime contract
- **Verification**:
  - `python3 -m pytest tests/runtime/ -x -q` -> `426 passed`
  - Import checks for `_run_job` and `ParallelExecutor` passed
  - Evidence captured at `.sisyphus/evidence/task-4-real-dispatch.txt` (no-CLI fallback path)

## [2026-03-05] Task 9: Ralph state file bridge

- **File**: `claude_experimental/parallel/ralph_bridge.py`
- **Ralph state format**: `{active: bool, iteration: int, max_iterations: int, original_prompt: str, started_at: ISO8601, checklist_path: str}`
- **State path**: `.omg/state/ralph-loop.json`
- **Pattern**: Bridge reads ralph-loop.json directly (no import of stop_dispatcher.py). Uses `_atomic_write()` with lazy import of `atomic_json_write` from `hooks/_common.py`, fallback to `tempfile + os.replace`.
- **Key design**: `signal_completion()` does upsert — removes existing entry for same job_id before appending, preventing duplicates.
- **Standalone safety**: All methods return safe defaults (False, {}, []) when state files don't exist.
- **Evidence**: `.sisyphus/evidence/task-9-ralph-missing.txt`, `task-9-ralph-read.txt`, `task-9-signal-completion.txt`

## [2026-03-05] Task 10: SQLite MemoryStore with WAL + FTS5

- **File**: `claude_experimental/memory/store.py`
- **Storage engine**: Added `MemoryStore` with stdlib `sqlite3`, connection-per-invocation access pattern, and default DB scope paths (`.omg/state/memory.db` / `~/.omg/memory.db`)
- **Schema setup**: Initializes `schema_info` + `memories` tables, `memories_fts` FTS5 virtual table, supporting indexes, and FTS sync triggers (`memories_ai`, `memories_ad`, `memories_au`)
- **Versioning + durability**: Persists `schema_version=1`; enables `PRAGMA journal_mode=WAL` (file DB) with `busy_timeout` and foreign-key enforcement
- **Retention policy**: Implements scope-level auto-prune at `MAX_ENTRIES_PER_SCOPE=10_000`, deleting lowest-importance and oldest-accessed rows first
- **Verification**:
  - `.sisyphus/evidence/task-10-wal-mode.txt` (in-memory instantiate/save/schema checks)
  - `.sisyphus/evidence/task-10-schema-version.txt` (FTS query probe)
  - `python3 -m pytest tests/claude_experimental/ -x -q` -> `11 passed`

## [2026-03-05] Task 5: send.parallel API

- Added claude_experimental/parallel/api.py with SendObject, IndividualResult, and ParallelResult dataclasses.
- Implemented distribution enums (BROADCAST, SHARD, ROUTED) and aggregation enums (BEST_RESULT, ALL_RESULTS, FIRST_SUCCESS).
- send_parallel() enforces feature flag gating via claude_experimental.parallel._require_enabled() and executes through ParallelExecutor.submit_many() plus wait_all().
- Verification evidence captured in .sisyphus/evidence/task-5-parallel-broadcast.txt and .sisyphus/evidence/task-5-flag-gate.txt.

## [2026-03-05] Task 6: Process Isolation via Subprocess Sandbox

- **File**: `claude_experimental/parallel/sandbox.py`
- **Class**: `SandboxedExecutor` — runs jobs in isolated Python subprocesses via `subprocess.Popen`
- **Spawn semantics**: Uses explicit `sys.executable` path with `start_new_session=True` (NOT fork)
- **Communication**: JSON over stdin/stdout pipes — args sent via `proc.communicate(input=...)`, structured result parsed from stdout
- **Worker script**: Built programmatically as list of lines (NOT `textwrap.dedent` with f-strings — that causes IndentationError when embedding multi-line blocks)
- **Memory limits**: `resource.setrlimit(resource.RLIMIT_AS, ...)` wrapped in try/except for Windows compat
- **Timeout**: `proc.communicate(timeout=N)` + `os.killpg()` + `proc.kill()` cascade for cleanup
- **Cleanup**: `atexit.register(_cleanup_all_children)` kills all tracked Popen processes on parent exit
- **Result schema**: `{schema_version, exit_code, stdout, stderr, pid, duration_ms, result, error}`
- **Feature flag**: Gated via `_require_enabled()` in `__init__`
- **Gotcha**: Never embed multi-line code blocks in f-strings with `textwrap.dedent` — the f-string substitution only indents the first line, causing IndentationError. Use list-of-strings approach instead.
- **Evidence**: `.sisyphus/evidence/task-6-pid-isolation.txt`, `.sisyphus/evidence/task-6-sandbox-cleanup.txt`
- **Commit**: `feat(parallel): add subprocess-based process isolation sandbox`

## [2026-03-05] Task 7: Dynamic Worker Pool Scaling

- **File**: `claude_experimental/parallel/scaling.py`
- **Class**: `DynamicPool` — wraps `ThreadPoolExecutor` with auto-scaling via background monitor thread
- **Scale-up**: `queue_depth > 2 × current_workers` → resize up to `max_workers` cap
- **Scale-down**: `queue_depth < 0.5 × current_workers` sustained for configurable hold period → shrink to `min_workers` floor
- **Config**: `min_workers=1`, `max_workers=100`, `scale_interval=10s`, `_SCALE_DOWN_HOLD_SECONDS=30s`
- **Resize strategy**: `ThreadPoolExecutor` doesn't support dynamic resizing, so `_resize()` swaps the executor instance. Old executor shutdown runs in a daemon thread (non-blocking).
- **Integration**: `runtime/subagent_dispatcher.py` `get_executor()` checks `PARALLEL_DISPATCH` flag via `_try_dynamic_pool()` — lazy singleton with `_dynamic_pool_checked` guard.
- **Critical bug found & fixed**: `_evaluate_scaling` called `_resize()` inside `with self._lock:` block in the scale-down path. Since `_resize()` also acquires `self._lock` (a non-reentrant `threading.Lock`), this caused a **deadlock**. Fix: compute `should_shrink` inside the lock, call `_resize()` outside.
- **Gotcha**: `threading.Lock` is NOT reentrant. If you need nested locking from the same thread, use `threading.RLock()` — or better, restructure so the inner call happens outside the lock.
- **Counter tracking**: `_queued`, `_active`, `_completed` tracked via `_wrapped()` decorator around submitted callables.
- **Evidence**: `.sisyphus/evidence/task-7-scale-up.txt`, `.sisyphus/evidence/task-7-scale-down.txt`
- **Verification**: `python3 -m pytest tests/runtime/ -x -q` → 426 passed (no regressions)
- **Commit**: `feat(parallel): add dynamic worker pool scaling`


## [2026-03-05] Task 8: Result aggregation with quality scoring

- **File**: `claude_experimental/parallel/aggregation.py`
- **Design**: Added pluggable `ResultAggregator` with `BestResultStrategy`, `AllResultsStrategy`, and `FirstSuccessStrategy`.
- **Quality formula**: `score = (exit_ok*0.4) + (length_score*0.2) + (time_score*0.2) + (no_error*0.2)` with component normalization to 0.0-1.0.
- **Heuristics**: `length_score` caps at 1000 chars, `time_score` decays to 0 at 30s, and `no_error` checks both `error` and `traceback` substrings case-insensitively.
- **ParallelResult assembly**: Aggregator returns `ParallelResult` with `aggregated` payload, pass/fail summary, and recipient-to-score ranking metadata.
- **Integration hook**: Added `strategy_for_mode()` and `aggregate_results(results, mode)` helper so `send_parallel()` can adopt strategy-based aggregation directly.
- **Evidence**: `.sisyphus/evidence/task-8-best-result.txt`, `.sisyphus/evidence/task-8-first-success.txt`


## [2026-03-05] Task 11: Episodic memory recording and recall

- **File**: `claude_experimental/memory/episodic.py`
- **Class/API**: Added `EpisodicMemory` with `record(...) -> int` and `recall(...) -> list[dict[str, object]]` using `MemoryStore`.
- **Feature gate**: `record()` and `recall()` both enforce memory availability via `claude_experimental.memory._require_enabled()` (resolved dynamically).
- **Scoring**: Importance policy implemented as success=0.7, failure with lessons=0.8, routine=0.3.
- **Temperature behavior**: Recall uses `min_score = 1.0 - temperature`; final relevance is rank-based to guarantee low-temp precision and high-temp diversity over returned candidates.
- **Event filtering**: Supports optional `event_type_filter` and validates event types (`success`, `failure`, `decision`, `discovery`).
- **Gotcha**: `MemoryStore(':memory:')` opens a fresh SQLite DB per connection with current store design, so round-trip checks should use a file-backed temp DB when save/search happen across separate calls.
- **Evidence**: `.sisyphus/evidence/task-11-episodic-roundtrip.txt`, `.sisyphus/evidence/task-11-temperature.txt`

## [2026-03-05] Task 15: Legacy Markdown Memory Migration Utility

- **File**: `claude_experimental/memory/migrate.py`
- **Function**: `migrate_markdown_memories(project_dir, target_store) -> dict[str, int]`
- **Purpose**: Migrate existing `.omg/state/memory/*.md` files to SQLite MemoryStore
- **Key features**:
  - Reads markdown files from `.omg/state/memory/` directory
  - Extracts date from filename (YYYY-MM-DD format) as created_at timestamp
  - Computes content hash via `hashlib.sha256(content.encode()).hexdigest()` for deduplication
  - Calculates importance: `min(len(content) / 500.0, 1.0)` (normalized to 500 chars)
  - Stores all memories as `memory_type="semantic"` with `scope="project"`
  - Preserves original markdown files (copy, don't move) for safe rollback
  - Idempotent: running twice doesn't create duplicates (dedup via content hash in metadata)
- **Metadata structure**: `{"content_hash": "...", "source_file": "...", "migrated_from": "markdown"}`
- **Return dict**: `{"files_found": int, "memories_migrated": int, "errors": int, "skipped_duplicates": int}`
- **Deduplication logic**: 
  - Before insert, query: `json_extract(metadata, '$.content_hash') = ?`
  - If match found: skip (increment skipped_duplicates)
  - If no match: insert new memory with metadata containing content_hash
- **Error handling**: Gracefully handles missing `.omg/state/memory/` directory (returns 0 files found)
- **Verification**:
  - Import check: `python3 -c "from claude_experimental.memory.migrate import migrate_markdown_memories; print('OK')"` ✓
  - Migration test: 3 sample files → 3 memories migrated, 0 errors ✓
  - Idempotency test: Second run → 0 new memories, 3 skipped duplicates ✓
  - Original files preserved: All 3 markdown files still exist after migration ✓
- **Evidence files**: 
  - `.sisyphus/evidence/task-15-migration.txt` (basic migration test)
  - `.sisyphus/evidence/task-15-idempotent.txt` (idempotency verification)
- **Commit**: `feat(memory): add markdown-to-SQLite memory migration utility`

## [2026-03-05] Task 13: Procedural Memory — Task Decomposition Knowledge

- **File**: `claude_experimental/memory/procedural.py`
- **Class/API**: `ProceduralMemory` with `store_procedure()`, `find_procedure()`, `record_outcome()`, `get_low_success_procedures()`
- **Storage**: Procedures stored as structured JSON in SQLite via `MemoryStore.save(content=JSON, memory_type="procedural")`
- **JSON schema**: `{task_type, steps, prerequisites, applicable_context, success_rate, use_count, schema_version}`
- **Success tracking**: Exponential Moving Average (EMA) with α=0.2: `new_rate = 0.8 * old_rate + 0.2 * observation`
- **FTS search strategy**: Uses OR-prefix query (`"implement* OR authentication*"`) for fuzzy matching since FTS5 unicode61 tokenizer splits on underscores (e.g., `auth_implementation` → tokens `auth`, `implementation`)
- **Update pattern**: `record_outcome()` uses direct `UPDATE memories SET content = ? WHERE id = ?` via `store.connect()`. FTS trigger `memories_au` handles sync automatically.
- **Gotcha**: `MemoryStore(':memory:')` opens fresh connection per call — must use file-backed temp DB for round-trip tests (same as episodic memory pattern)
- **Gotcha**: basedpyright requires `cast(int | float | str, parsed.get(...))` before `float()` / `int()` calls on dict `.get()` returns typed as `object`
- **Evidence**: `.sisyphus/evidence/task-13-procedure-roundtrip.txt`, `.sisyphus/evidence/task-13-success-tracking.txt`
- **Commit**: `feat(memory): implement procedural memory with success rate tracking`

## [2026-03-05] Task 12: Semantic memory with FTS5 scoring and entity links

- **File**: `claude_experimental/memory/semantic.py`
- **Class/API**: `SemanticMemory` with `store_fact()`, `search()`, `add_link()`, `get_links()`, `consolidate()`
- **Scoring formula**: `BM25_norm * 0.4 + importance * 0.3 + recency * 0.2 + access_freq * 0.1`
- **BM25 normalization**: FTS5 `bm25()` returns negative values (more negative = better). Normalized via `(worst - raw) / range` so higher = better match.
- **Recency**: Linear decay over 7 days (`1.0 - age / 604800`), clamped to [0, 1].
- **Access frequency**: `count / max_count` across current result set.
- **Entity links**: Separate `semantic_links` table in same SQLite DB with `(from_entity, to_entity, relationship_type, created_at)`. Bidirectional lookup (WHERE from = ? OR to = ?).
- **`:memory:` gotcha**: Each `store.connect()` opens fresh in-memory DB. `_connect_with_links()` re-creates links table per connection to handle this. For round-trip tests, use file-backed temp DB.
- **Consolidation**: Word-level Jaccard similarity. Entries sorted by importance DESC — higher-importance entries survive, lower ones get deleted with access_count folded in.
- **FTS5 query syntax**: Use `OR` for disjunctive queries (`"auth OR login"`). Plain space is implicit AND. Prefix matching needs `*` suffix.
- **basedpyright**: Avoid implicit string concatenation (adjacent `"foo" "bar"` literals). Use triple-quoted strings for SQL or single-line strings. Assign unused cursor results to `_`.
- **Evidence**: `.sisyphus/evidence/task-12-fts5-scoring.txt`, `.sisyphus/evidence/task-12-semantic-links.txt`
- **Commit**: `feat(memory): implement semantic memory with FTS5 scoring and entity links`

## [2026-03-05] Task 16: AST Pattern Extraction Engine

- **File**: `claude_experimental/patterns/extractor.py`
- **Class/API**: `ASTExtractor.extract(file_path) -> PatternCollection` with `Pattern` dataclass (`type`, `name`, `frequency`, `location`, `snippet`)
- **Feature gate**: `extract()` dynamically resolves and invokes `claude_experimental.patterns._require_enabled()`; disabled flag raises runtime error from tier gate
- **Python extraction**: Uses stdlib `ast.parse()` + `ast.walk()` for function defs (sync/async), classes, class hierarchies, imports, try/except, loops (`for`/`while`), and conditionals (`if`)
- **Fallback extraction**: Non-`.py` files use regex for `def`, `class`, `import`, and JavaScript-style `function` declarations
- **Cache design**: Class-level `_cache: dict[str, PatternCollection]`, keyed by `sha256(file_content)`, returns cached results for unchanged content without reparsing
- **Frequency policy**: Repeated `(type, name)` entries are counted and embedded into each emitted `Pattern.frequency`
- **Evidence**: `.sisyphus/evidence/task-16-ast-extraction.txt`, `.sisyphus/evidence/task-16-cache-hit.txt`
- **Verification snapshot**: `hooks/_common.py` produced 81 patterns (17 functions); second extraction faster (`0.00007158s` vs `0.00022563s`) with cache hit confirmed

## [2026-03-05] Task 14: Public remember/recall/memory_check API

- **File**: `claude_experimental/memory/api.py`
- **Public API**: Added `remember(...)`, `recall(...)`, and `memory_check(...)` with `RetrievedMemory` dataclass.
- **Feature-gate pattern**: Uses dynamic resolver `_require_memory_enabled()` to call `claude_experimental.memory._require_enabled()` without direct private import (keeps strict pyright clean).
- **Auto-detection rules**: `remember(memory_type='auto')` maps to procedural when content contains `Step `, `steps:`, or numbered list; episodic when content contains `event:`, `outcome:`, `fixed`, or `resolved`; otherwise semantic.
- **Unified recall pattern**: `recall()` queries semantic + episodic + procedural memories, normalizes relevance to 0-1, merges, deduplicates by `(source_type, memory_id, content)`, then sorts descending by `relevance_score`.
- **Integrity check pattern**: `memory_check()` runs `PRAGMA integrity_check`, optional repair (`REINDEX` + `VACUUM`), optional compaction (`VACUUM`), and returns typed DB stats (`total_memories`, grouped by type and scope).
- **Verification evidence**: `.sisyphus/evidence/task-14-auto-detect.txt`, `.sisyphus/evidence/task-14-unified-recall.txt`

## [2026-03-05] Task 18: Anti-Pattern Detection and Code Quality Scoring

- **File**: `claude_experimental/patterns/antipatterns.py`
- **Class/API**: `AntiPatternDetector` with `detect(file_path) -> list[AntiPatternViolation]`, `score(file_path) -> float`, `add_rule(rule_fn)`
- **Data model**: `AntiPatternViolation` dataclass with `rule_name`, `severity` (critical/high/medium/low), `line`, `description`, `snippet`
- **10 built-in detectors**:
  1. `bare_except` — bare `except:` without specific type (AST, high)
  2. `mutable_default` — mutable default args `[]`/`{}`/`set()` (AST, high)
  3. `type_ignore_no_reason` — `# type: ignore` without `[code]` (regex, medium)
  4. `god_class` — >20 methods or >500 lines (AST, critical)
  5. `deep_nesting` — >4 indentation levels (regex, medium)
  6. `long_function` — >100 lines (AST, medium)
  7. `unused_import` — imports not referenced in AST names (AST, low)
  8. `print_statement` — `print()` in non-test/debug files (regex, low)
  9. `empty_except` — `except: pass` or `except: ...` (AST, high)
  10. `magic_number` — numeric literals outside safe set {0,1,-1,2,100,0.5} (AST, low)
- **Scoring formula**: `score = max(0.0, 1.0 - sum(severity_weights) / 1.5)` with weights: critical=0.3, high=0.2, medium=0.1, low=0.05
- **Feature gate**: Both `detect()` and `score()` call `_require_enabled()` from `claude_experimental.patterns`
- **score() pattern**: `score()` calls `_require_enabled()` then uses `_detect_raw()` internally to avoid double feature-flag checking
- **basedpyright gotcha**: Can't access `self.detect.__wrapped__` — pyright flags it as unknown attribute on `MethodType`. Use a separate internal method instead.
- **Unused import detector**: Also checks string occurrences via regex as fallback for TYPE_CHECKING blocks; skips underscore-prefixed imports
- **Magic number exclusions**: Skips UPPER_CASE constant definitions, `__dunder__` assignments, decorator lines, comments
- **Evidence**: `.sisyphus/evidence/task-18-bare-except.txt`, `.sisyphus/evidence/task-18-quality-score.txt`
- **Commit**: `feat(patterns): implement anti-pattern detection with quality scoring`

## [2026-03-05] Task 23: Human-in-the-Loop Checkpoint System

- **File**: `claude_experimental/integration/checkpoints.py`
- **Class/API**: `CheckpointManager` with `create_checkpoint()`, `get_checkpoint()`, `resume_checkpoint()`, `list_pending()`, `cleanup_expired()`
- **Checkpoint types**: `VERIFICATION`, `DECISION`, `CLARIFICATION` (via `CheckpointType` str enum)
- **State persistence**: Individual JSON files at `.omg/state/checkpoints/{uuid}.json` with atomic write (tempfile + `os.replace()`)
- **JSON schema**: `{checkpoint_id, type, description, options, status, decision, created_at, expires_at, schema_version}`
- **Auto-expiry**: `get_checkpoint()`, `list_pending()`, and `resume_checkpoint()` all auto-transition pending→expired when `expires_at < now`
- **Cleanup**: `cleanup_expired()` physically deletes expired checkpoint files from disk
- **Feature gate**: All public methods call `_require_integration()` which delegates to `claude_experimental.integration._require_enabled()`
- **Atomic write pattern**: Used `tempfile.mkstemp()` + `os.fdopen()` + `os.replace()` instead of the simpler `path + ".tmp"` approach — mkstemp avoids collisions if multiple processes write concurrently
- **Gotcha**: `.sisyphus/` is in `.gitignore` — need `git add -f` for evidence files
- **Evidence**: `.sisyphus/evidence/task-23-checkpoint-lifecycle.txt` (full lifecycle: create, list, resume, re-resume, expired cleanup, invalid type, flag gate)
- **Commit**: `feat(integration): implement human-in-the-loop checkpoint system`

## [2026-03-05] Task 17: Pattern Mining with Frequency Counters and Deviation Scoring

- **File**: `claude_experimental/patterns/mining.py`
- **Class/API**: `PatternMiner.mine(directory, min_support=0.05, pattern_type='sequential') -> PatternReport`
- **Report model**: Added `PatternReport` dataclass with `patterns`, `frequencies`, `deviations`, `baseline`, `total_files`
- **Feature gate pattern**: `mine()` dynamically resolves and invokes `claude_experimental.patterns._require_enabled()` to keep private-import diagnostics clean
- **Pattern modes**:
  - `sequential`: converts adjacent import statements into chain signatures (`import_a->import_b`)
  - `structural`: mines `class_hierarchy` patterns emitted by `ASTExtractor`
- **Frequency/support**: Uses `collections.Counter` for total occurrences and per-file support; `min_support` threshold is enforced as minimum supporting file count
- **Sliding windows**: Builds overlapping file-order windows (`window_size = isqrt(total_files)`) and computes per-pattern window counts
- **Deviation scoring**: Computes z-score per pattern as `(peak_window_frequency - mean_window_frequency) / std_dev_window_frequency`, with anomaly threshold `abs(z) > 2.0`
- **Baseline**: Stores global mean/std-dev for selected pattern frequencies plus configured anomaly threshold metadata
- **Evidence**: `.sisyphus/evidence/task-17-pattern-detection.txt`, `.sisyphus/evidence/task-17-deviation-scoring.txt`
- **Commit**: `feat(patterns): implement frequency-based pattern mining with deviation scoring`

## [2026-03-05] Task 24: Telemetry Collection and Metrics Store

- **File**: `claude_experimental/integration/telemetry.py`
- **Class/API**: `TelemetryCollector` with `record_counter()`, `record_gauge()`, `record_histogram()`, `query()`, `aggregate()`, `rotate_old_data()`
- **Storage**: Separate SQLite DB at `.omg/state/telemetry.db` (not shared with memory DB)
- **Schema**: `metrics` table (`id INTEGER PK`, `name TEXT`, `metric_type TEXT`, `value REAL`, `tags TEXT JSON`, `recorded_at TEXT ISO8601`, `schema_version INTEGER DEFAULT 1`) + `schema_info` table (`key TEXT PK`, `value TEXT`)
- **WAL mode**: `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` at connection creation
- **Connection pattern**: Connection-per-invocation, no pooling (same as MemoryStore)
- **Feature gate**: Constructor + all public methods call `_require_enabled()` from `claude_experimental.integration`
- **Aggregation**: Uses `substr(recorded_at, 1, N)` for period bucketing (minute/hour/day) — avoids strftime SQLite extension dependency
- **Privacy**: Only numeric metrics. No content capture. Local-only storage.
- **Rotation**: `rotate_old_data(days=30)` deletes `WHERE recorded_at < cutoff_iso`
- **QA verified**: 100-counter round-trip with aggregation sum=100, gauge/histogram types, old data rotation (5 of 7 rows deleted)
- **Evidence**: `.sisyphus/evidence/task-24-counter.txt`
- **Commit**: `feat(integration): implement local telemetry collection and metrics store`

## [2026-03-05] Task 21: OpenAPI schema-driven tool generation

- **File**: `claude_experimental/integration/openapi_gen.py`
- **Class/API**: `ToolGenerator.generate(spec_path)` and `ToolGenerator.generate_module(spec_path)`
- **Feature gate pattern**: Resolved `claude_experimental.integration._require_enabled` dynamically via module import + `__dict__` lookup to keep strict diagnostics clean while still invoking the integration guard.
- **Spec parsing**: JSON specs use `json.loads`; YAML specs use a minimal indentation parser with inline flow support for `{k: v}` and `[a, b]` forms used in OpenAPI schemas.
- **Parameter mapping**: Path parameters are positional args (with generated callable signatures via `inspect.Signature`), query parameters are `**query_params`, and body payload is `body` dict encoded to JSON.
- **HTTP transport**: Uses stdlib `urllib.request.Request` + `urlopen` only (no external HTTP dependency).
- **Response handling**: Empty response returns `{}`; JSON object returns dict directly; non-object JSON is wrapped as `{"data": ...}`.
- **Error mapping**: `HTTPError` code `404 -> FileNotFoundError`, `400 -> ValueError`, `>=500 -> RuntimeError`.
- **Verification**: Import check passed, 2-endpoint JSON spec produced 2 generated callables, and mocked 404 raised `FileNotFoundError`.
- **Evidence**: `.sisyphus/evidence/task-21-openapi-gen.txt`, `.sisyphus/evidence/task-21-error-handling.txt`

## [2026-03-05] Task 22: SSE Streaming for Agent Output

- **File**: `claude_experimental/integration/streaming.py`
- **Class/API**: `SSEStream` with `emit(event_type, data, event_id=None)`, `read(last_event_id=None)`, `close()`
- **Constructor**: `SSEStream(max_buffer=100)` — bounded buffer with auto-drop on overflow
- **Buffer implementation**: `collections.deque(maxlen=max_buffer)` for FIFO backpressure
- **Thread safety**: `threading.Lock` protects all buffer access in `emit()` and `read()`
- **SSE format**: RFC 9110 compliant — `id: {uuid}\nevent: {type}\ndata: {payload}\n\n`
- **Event ID generation**: Auto-generates UUID via `uuid.uuid4()` if not provided
- **Resumable streams**: `read(last_event_id=...)` skips events before and including the given ID
- **Feature gate**: Both `emit()` and `read()` call `_require_enabled()` from `claude_experimental.integration`
- **Close semantics**: `close()` sets `_closed` flag; subsequent `emit()` raises `RuntimeError`
- **Event types supported**: `content`, `progress`, `error`, `complete` (custom types allowed)
- **Stdlib-only**: Uses only `threading`, `uuid`, `collections.deque`, `typing` (no external deps)
- **QA verified**:
  - ✓ Basic emit/read with SSE format compliance
  - ✓ Backpressure: 200 events → 100 in buffer (oldest dropped)
  - ✓ Thread safety: 5 threads × 20 events each → all 100 captured
  - ✓ last_event_id filtering: resume from event 3 → 2 events returned
  - ✓ close() behavior: RuntimeError on emit after close
  - ✓ Feature flag gating: RuntimeError when disabled
- **Evidence**: `.sisyphus/evidence/task-22-sse-format.txt` (comprehensive format + backpressure + thread safety verification)
- **Commit**: `feat(integration): implement SSE streaming for agent output`

## [2026-03-05] Task 19: Unified patterns API (detect/validate/synthesize)

- **File**: `claude_experimental/patterns/api.py`
- **Public API**: Added `pattern_detect(path, min_support=0.05, pattern_type='sequential')`, `pattern_validate(candidate_pattern, against_path, min_support=0.05)`, and `pattern_synthesize(template, constraints=None)`.
- **Report models**: Exposed `PatternReport` and added `ValidationReport` (`pattern`, `support`, `is_valid`, `violations`, `confidence`) plus `SynthesisResult` (`template`, `suggestions`, `confidence`).
- **Feature gate pattern**: All public functions call a local `_require_patterns_enabled()` helper that dynamically invokes `claude_experimental.patterns._require_enabled()`.
- **Validation logic**: Support computed as `frequency / total_files`; validity threshold defaults to `0.05`; anti-pattern violations are aggregated across the target path and included as formatted entries.
- **Anti-pattern integration**: `pattern_detect()` enriches returned `PatternReport` with `antipattern:*` keys in frequencies/deviations and anti-pattern summary counters in `baseline`.
- **Synthesis scope**: Intentionally template-only suggestions with optional constraint annotations (no neural/codegen implementation).
- **Type-checking gotcha**: Importing private tier helpers directly triggers strict diagnostics; dynamic module lookup keeps type checks clean while preserving required flag enforcement.
- **Evidence**: `.sisyphus/evidence/task-19-pattern-workflow.txt`

## [2026-03-05] Task 20: Automated Refactoring Suggestion Engine

- **File**: `claude_experimental/patterns/refactoring.py`
- **Class/API**: `RefactoringSuggester` with `suggest(file_path) -> RefactoringSuggestionReport`
- **Data models**:
  - `RefactoringSuggestion`: `rule_name`, `severity`, `line`, `description`, `transformation`, `effort` (low/medium/high)
  - `RefactoringSuggestionReport`: `file_path`, `suggestions`, `total_score`, `summary`
- **Internal dependency**: Uses `AntiPatternDetector` internally — `detect()` for violations, `score()` for quality metric
- **Rule mapping**: 10 anti-pattern rules mapped to natural-language transformation descriptions with effort estimates:
  - low-effort (6): `bare_except`, `mutable_default`, `unused_import`, `print_statement`, `empty_except`, `magic_number`
  - medium-effort (3): `deep_nesting`, `long_function`, `type_ignore_no_reason`
  - high-effort (1): `god_class`
- **Sort order**: Suggestions sorted by severity (critical=0, high=1, medium=2, low=3) so critical issues surface first
- **Unknown rule handling**: Rules not in `_REFACTORING_MAP` get generic "Review and address: {description}" with effort=medium
- **Summary format**: `"{file}: N suggestion(s); quality score: X.XX; by severity: ...; by effort: ..."`
- **Feature gate**: `suggest()` calls `_require_enabled()` from `claude_experimental.patterns` (same pattern as AntiPatternDetector)
- **Import cleanup**: Removed unused `field` import from dataclasses; used `AntiPatternDetector | None` instead of deprecated `Optional[AntiPatternDetector]`
- **Note on `type_ignore`**: Task spec says `type_ignore` but actual rule name in antipatterns.py is `type_ignore_no_reason` — used the actual rule name for correct mapping
- **Evidence**: `.sisyphus/evidence/task-20-refactoring-suggestions.txt`
- **Commit**: `feat(patterns): implement automated refactoring suggestion engine`

## [2026-03-05] Task 25: A/B Experiment Tagging Framework

- **File**: `claude_experimental/integration/experiments.py`
- **Class/API**: `ExperimentTracker` with `define_experiment()`, `assign_variant()`, `tag_metric()`, `compare()`
- **Storage**: Shared SQLite DB at `.omg/state/telemetry.db` (same as TelemetryCollector)
- **Schema**: `experiments` table (id, name, variants JSON, assignment, created_at, schema_version) + `experiment_metrics` table (experiment_id FK, variant, metric_name, value, recorded_at, schema_version)
- **WAL mode**: `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` (same as TelemetryCollector)
- **Connection pattern**: Connection-per-invocation for file-backed DBs; persistent shared connection for in-memory DBs (test support)
- **Variant assignment**:
  - Hash-based (deterministic): `SHA256(experiment_id:subject_id) % num_variants` — same subject always gets same variant
  - Random (default): `random.choice(variants)` — each call may assign different variant
- **Comparison output**: `{variant_name: {count: int, mean: float, min: float, max: float}, ...}`
- **Feature gate**: All public methods call `_require_enabled()` from `claude_experimental.integration`
- **In-memory DB gotcha**: Closing last connection to shared `:memory:` DB destroys it. Solution: maintain `_shared_memory_conn` in `__init__` and only close file-backed connections in finally blocks.
- **QA verified**: 
  - Variant comparison: small (count=2, mean=110), large (count=1, mean=80) ✓
  - Hash assignment deterministic: user_123 → treatment (consistent) ✓
  - Random assignment: produced all 3 variants across 10 subjects ✓
- **Evidence**: `.sisyphus/evidence/task-25-experiment.txt`
- **Commit**: `feat(integration): implement A/B experiment tagging framework`

## [2026-03-05] Task 26: Automatic Parameter Tuning from Telemetry

- **File**: `claude_experimental/integration/autotuner.py`
- **Class/API**: `AutoTuner` with `tune_cycle()` and `get_current_params()`
- **Constructor**: `AutoTuner(pool, telemetry, min_workers=1, max_workers=8, target_p99_ms=5000)`
- **Tuning rules** (threshold-based, no Bayesian):
  - Scale UP: P99 latency > 2× target → `pool._resize(current + 1)` (capped at max_workers)
  - Scale DOWN: utilization < 30% sustained for >30s → `pool._resize(current - 1)` (floored at min_workers)
- **P99 computation**: Query `task_duration_ms` histogram metrics (last 5 min), sort values, ceiling-based 99th percentile index
- **Utilization**: `active / pool_size` from `pool.pool_stats()`
- **Hysteresis**: Scale-down uses `_low_util_since` timestamp (same pattern as DynamicPool's `_low_since`)
- **Telemetry logging**: All decisions logged via `telemetry.record_counter("autotuner_adjustment", value=1, tags={"direction": "up"/"down", "reason": "..."})`
- **Feature gate**: Constructor + `tune_cycle()` + `get_current_params()` all call `_require_enabled()` from `claude_experimental.integration`
- **`:memory:` DB gotcha**: TelemetryCollector with `:memory:` opens fresh SQLite DB per `_connect()` call — data is lost between connections. Must use file-backed temp DB for QA scenarios.
- **basedpyright fix**: `row["value"]` returns `object` from `query()` — needs `cast(float, row["value"])` for sorted() comparison
- **Evidence**: `.sisyphus/evidence/task-26-autotune.txt`
- **Commit**: `feat(integration): implement automatic parameter tuning from telemetry`

## [2026-03-05] Task 28: Memory-augmented prompt enrichment

- **File**: `claude_experimental/memory/augmented_generation.py`
- **Class/API**: `MemoryAugmenter` with `augment_prompt()`, `record_outcome()`, `get_contribution_stats()`
- **Feature gate pattern**: Added `_require_memory_enabled()` helper that dynamically resolves `claude_experimental.memory._require_enabled`; all public methods invoke it.
- **Fail-safe behavior**: `augment_prompt()` returns base prompt unchanged when memory is disabled, when no memories are recalled, or on any exception.
- **Prompt injection format**: Prepends exact section header `## Relevant Context from Memory`, numbered recalled memories with relevance/type, delimiter `---`, then original prompt.
- **Outcome tracking**: Added lazy-created `augmentation_outcomes` SQLite table (`memory_id`, `prompt_hash`, `success`, `created_at`) in memory DB, plus per-memory success-rate aggregation via `AVG(success)`.
- **Recall gotcha**: `recall()` default `min_relevance=0.5` can filter weaker matches; QA data should include close lexical overlap with query to guarantee injected context.
- **Evidence**: `.sisyphus/evidence/task-28-memory-augment.txt`

## [2026-03-05] Task 29: Feature Flag Lifecycle Management

- **File**: `claude_experimental/_lifecycle.py`
- **Class/API**: `FeatureFlagLifecycle` with `register()`, `check_health()`, `use_feature()`, `get_registry()`
- **Enum**: `LifecycleStage` with values: `ALPHA = "alpha"`, `BETA = "beta"`, `STABLE = "stable"`, `DEPRECATED = "deprecated"`
- **Singleton pattern**: Module-level `_DEFAULT_LIFECYCLE` instance with all 5 experimental flags pre-registered as ALPHA
- **Pre-registered flags**: PARALLEL_DISPATCH, EXPERIMENTAL_MEMORY, PATTERN_INTELLIGENCE, ADVANCED_INTEGRATION, ULTRAWORKER
- **Alpha warning**: `use_feature()` on ALPHA feature writes to stderr: `[OMG ALPHA] Feature '{flag_name}' is alpha. Behavior may change.`
- **Deprecated warning**: `use_feature()` on DEPRECATED feature writes to stderr: `[OMG DEPRECATED] Feature '{flag_name}' is deprecated. Please migrate.`
- **No feature gate**: This is meta-management, always available regardless of flags
- **Type hints**: Used `dict[str, dict[str, str]]` instead of `Any` to keep basedpyright clean
- **stderr handling**: Assigned `sys.stderr.write()` result to `_` to suppress unused-call-result warnings
- **Evidence**: `.sisyphus/evidence/task-29-alpha-warning.txt` (QA scenario with alpha/deprecated warnings verified)
- **Verification**: `python3 -m pytest tests/claude_experimental/ -x -q` → 11 passed (no regressions)
- **Commit**: `feat(experimental): implement feature flag lifecycle management`

## [2026-03-05] Task 27: Ultraworker high-throughput router

- **File**: `claude_experimental/parallel/ultraworker.py`
- **Class/API**: `UltraworkerRouter` with `submit`, `submit_batch`, `wait_for_results`, `get_stats`, `shutdown`
- **Queue pattern**: Priority queue items are `(-priority, sequence_num, job_id, task_info)` so higher priorities dispatch first
- **Batching pattern**: `submit_batch()` normalizes a shared `batch_id` and dispatches via `ParallelExecutor.submit_many()`
- **Aggregation pattern**: `wait_for_results()` resolves executor IDs, waits with `wait_all()`, then aggregates via `ResultAggregator(strategy_for_mode(...))`
- **Flag gate**: Added `ULTRAWORKER` to `claude_experimental/_flags.py` known flags; all public router methods enforce `get_feature_flag("ULTRAWORKER", default=False)`
- **Cost tracking**: `_total_cost_units` increments by 1 per submitted task and is exposed in `get_stats()`
- **Evidence**: `.sisyphus/evidence/task-27-priority.txt`
- **Verification**: `python3 -m pytest tests/claude_experimental/ -x -q` -> `11 passed`

## [2026-03-05] Task 34: Comprehensive Tier-3 Pattern Intelligence test suite

- **Files created**: 5 test files in `tests/claude_experimental/tier3/`:
  - `test_extractor.py` (8 tests): extract from real .py, finds functions/classes, cache hit, empty file, syntax error regex fallback, non-Python regex, pattern fields
  - `test_mining.py` (5 tests): mine directory returns report, sequential patterns with chains, empty dir, invalid pattern_type ValueError, baseline keys
  - `test_antipatterns.py` (7 tests): bare_except, mutable_default, deep_nesting, clean file >0.9, dirty file <0.5, add_custom_rule, empty_except
  - `test_api.py` (6 tests): pattern_detect returns report, detects antipatterns in frequencies, pattern_validate returns ValidationReport, validate with Pattern object, synthesize basic, synthesize with constraints
  - `test_refactoring.py` (5 tests): deep nesting suggestions, clean file no suggestions, multiple issues prioritized, summary contains path, effort field present
- **Total**: 31 tests passing (target was ≥20)
- **All tests use** `@pytest.mark.experimental` marker
- **Feature flag**: Used `feature_flag_enabled("PATTERN_INTELLIGENCE")` conftest fixture (autouse)
- **Cache safety**: `ASTExtractor._cache.clear()` in autouse fixtures prevents cross-test leaks (class-level dict)
- **All existing tests preserved**: 176 total tests pass (including 11 original + other tier tests)
- **Commit**: `test(patterns): add comprehensive Tier-3 test suite`

## [2026-03-05] Task 35: Comprehensive Tier-4 Integration Test Suite

- **Files created**: 6 test files in `tests/claude_experimental/tier4/`
  - `test_openapi.py` (7 tests): generate/callable/404→FileNotFoundError/malformed spec/empty paths/disabled flag
  - `test_streaming.py` (10 tests): emit/read round-trip, SSE format, FIFO order, backpressure 200→100, last_event_id filtering, close semantics, feature gate
  - `test_checkpoints.py` (10 tests): create/get/list/resume lifecycle, resolved excluded from pending, auto-expiry, cleanup_expired, invalid type, nonexistent KeyError, feature gate
  - `test_telemetry.py` (8 tests): counter/gauge/histogram recording + query, tags round-trip, aggregate sum/min/max/avg, rotate_old_data, feature gate
  - `test_experiments.py` (7 tests): define_experiment, hash deterministic assignment, random assignment, tag_metric + compare per-variant stats, empty compare, feature gate
  - `test_autotuner.py` (9 tests): high latency scale-up, normal latency no change, max_workers cap, get_current_params, no-data no-adjustment, invalid min_workers/target_p99, feature gate
- **Total**: 51 tests passing (requirement was ≥20)
- **All tests**: Use `@pytest.mark.experimental` marker on test classes
- **Feature flag**: `autouse=True` fixture with `monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")` per module
- **File-backed DBs**: Used `tmp_path / "telemetry.db"` for TelemetryCollector, ExperimentTracker, AutoTuner (avoids :memory: cross-connection gotcha)
- **CheckpointManager**: Passed `base_dir=str(tmp_path)` to constructor (creates .omg/state/checkpoints/ under tmp_path)
- **AutoTuner pool cleanup**: Used `yield` fixture with `p.shutdown(wait=False)` in finally/teardown
- **Existing tests**: 11 tests in test_package_init.py still passing (no regressions)
- **Mocking pattern**: Used `@patch("claude_experimental.integration.openapi_gen.request.urlopen")` for ToolGenerator HTTP tests
- **Commit**: `test(integration): add comprehensive Tier-4 test suite`


## [2026-03-05] Task 36: Cross-tier integration tests

- **File**: `tests/claude_experimental/test_cross_tier.py`
- **Coverage added**:
  - Tier independence: memory tier operates with `OMG_EXPERIMENTAL_MEMORY_ENABLED=1` while Tier-1 parallel submit raises `RuntimeError` when disabled.
  - Graceful degradation: `GracefulDegradation(DegradationTier.CIRCUIT_BREAKER)` returns fallback payload on tier failure.
  - Lifecycle: `FeatureFlagLifecycle().check_health()` validated against all five experimental flags (`PARALLEL_DISPATCH`, `EXPERIMENTAL_MEMORY`, `PATTERN_INTELLIGENCE`, `ADVANCED_INTEGRATION`, `ULTRAWORKER`).
  - Memory + pattern: `ASTExtractor` output and `MemoryAugmenter` prompt enrichment verified in same test context.
  - Telemetry + parallel: `TelemetryCollector` records histogram/counter metrics produced from `DynamicPool` operations; aggregate and query verified.
  - Failure learning + memory: `FailureLearner.record_failure()` and `suggest_fix()` round-trip against file-backed memory DB.
- **Gotchas**:
  - `MemoryAugmenter.augment_prompt()` depends on `recall()` lexical match and relevance threshold; punctuation-heavy prompts can cause no-memory fallback. Stable tests use tokenized query/memory text with high importance.
  - Keep Tier-1 coverage dispatch-free by using `ParallelExecutor().submit(...)` only in disabled-path assertion to avoid real agent calls.
- **Verification**:
  - `python3 -m pytest tests/claude_experimental/test_cross_tier.py -x -q` -> `6 passed`
  - `python3 -m pytest tests/claude_experimental/ -x -q` -> `190 passed`
  - `lsp_diagnostics tests/claude_experimental/test_cross_tier.py` -> clean
