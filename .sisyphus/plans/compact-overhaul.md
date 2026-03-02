# Compact Overhaul — Fix Deadlock, Consolidate Hooks, Proactive Compaction

## TL;DR

> **Quick Summary**: Fix the context-limit deadlock where stop hooks block compaction, consolidate 3 independent stop hook groups into 1 dispatcher, enhance state preservation through compaction, and add proactive auto-handoff before context limits are hit.
> 
> **Deliverables**:
> - Deadlock-proof stop hook system (zero blocking on context-limit stops)
> - Single consolidated stop hook entry in `~/.claude/settings.json`
> - Enhanced pre-compact state preservation (checklist progress, current task, failure history)
> - Proactive context pressure detection with auto-handoff
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 → Task 4 → Task 6 → Task 11 → Final Verification

---

## Context

### Original Request
User experiences intermittent deadlock: typing ".." (continue) when context is full triggers stop hooks that block the stop, preventing compaction. The "Planning gate: 72/120 complete, 48 pending" error fires from `check_planning_gate()` and Claude can't resolve it because context is exhausted.

### Interview Summary
**Key Discussions**:
- ".." is NOT a shortcut — it's a continuation prompt
- Deadlock is intermittent, not every session
- User wants auto-compact + continue (zero intervention)
- ALL priorities selected: deadlock fix, consolidation, phantom cleanup, proactive compaction, better context survival
- Context survival: checklist progress, current task context, AND failure history must survive
- Proactive: auto-handoff at threshold, not just warning

**Research Findings**:
- `test-validator.py` does NOT call `should_skip_stop_hooks()` — biggest deadlock contributor
- `quality-gate.py` EXISTS at `~/.claude/hooks/` (102 lines) — NOT phantom. Contains useful bare-done detection logic
- `stop_reason`/`end_turn_reason` fields do NOT exist in Stop hook payloads — Guard 3 in `_common.py:276-298` is dead code
- 3 separate Stop hook groups in `~/.claude/settings.json` run in parallel — any single group blocking causes deadlock
- `_BLOCK_LOOP_THRESHOLD = 2`, `_BLOCK_LOOP_WINDOW_SECS = 30` — Guard 4 only catches on THIRD attempt
- `.stop-block-tracker.json` has race conditions when parallel hook groups write simultaneously
- Pre-compact: snapshots 7 files, generates handoff.md truncated at 60 lines
- Ralph loop blocks stops at P1 priority (before planning gate)

### Metis Review
**Identified Gaps** (addressed):
- `quality-gate.py` is NOT phantom — logic must be PRESERVED, not removed. Absorb into stop_dispatcher.py
- `test-validator.py` missing `should_skip_stop_hooks()` is the single biggest deadlock contributor
- Guard 3 (`stop_reason` patterns) is dead code — these fields don't exist in Stop hook payloads
- Guard 5 false positives: legitimate quality block + quick normal stop within 30s incorrectly skips gates. Must track block REASON
- `.stop-block-tracker.json` needs `session_id` to prevent cross-session interference
- `quality-runner.py` runs 60s subprocess during first context-limit stop — wastes time before deadlock cycle
- PreCompact may not fire on auto-compact (Bug #26010) — need fallback state capture
- Concurrent sessions share tracker file — needs session isolation

---

## Work Objectives

### Core Objective
Eliminate the context-limit deadlock in the stop hook system and make compaction seamless — stop hooks never block when context is exhausted, state is preserved through compaction, and proactive detection prevents hitting the wall.

### Concrete Deliverables
- `hooks/test-validator.py` — patched with `should_skip_stop_hooks()` guard
- `hooks/_common.py` — Guard 3 dead code removed, tracker enhanced with `session_id` + `reason`, Guard 5 updated
- `hooks/stop_dispatcher.py` — absorbs `quality-gate.py` logic as a new check function
- `~/.claude/hooks/quality-gate.py` — removed (logic absorbed into dispatcher)
- `~/.claude/settings.json` — 3 Stop groups consolidated into 1
- `hooks/pre-compact.py` — enhanced state capture (ralph-loop.json, richer handoff)
- `hooks/prompt-enhancer.py` — proactive context pressure detection + auto-handoff injection
- `hooks/quality-runner.py` — short-circuits subprocess when context pressure detected
- `OAL-setup.sh` — updated stop hook consolidation logic

### Definition of Done
- [x] No deadlock when context is full and stop hooks fire
- [x] `should_skip_stop_hooks()` called by ALL stop hooks (test-validator, quality-gate absorbed, quality-runner, stop_dispatcher)
- [x] Single Stop hook group in `~/.claude/settings.json`
- [x] Guard 3 dead code removed from `_common.py`
- [x] `.stop-block-tracker.json` includes `session_id` and `reason`
- [x] Pre-compact captures ralph-loop state and expands beyond 60-line limit
- [x] Proactive context pressure warning injected at tool-call threshold
- [x] All existing quality gate checks STILL BLOCK on normal (non-context-limit) stops

### Must Have
- test-validator.py calls `should_skip_stop_hooks()` at the top
- quality-gate.py bare-done detection logic preserved in stop_dispatcher.py
- Guard 5 tracks block reason (not just count) to prevent false positives
- Pre-compact captures ralph-loop.json state in handoff
- Planning gate demotes to advisory under context pressure
- Session isolation in `.stop-block-tracker.json`

### Must NOT Have (Guardrails)
- DO NOT remove any check function from stop_dispatcher.py — all 10 checks are proven quality gates
- DO NOT change blocking behavior for normal (non-context-limit) stops
- DO NOT weaken quality gates when "maybe" near limit — only demote on confirmed context pressure
- DO NOT remove quality-gate.py without absorbing its logic first
- DO NOT make Guard 5 skip quality gates after legitimate (non-loop) blocks
- DO NOT touch Ralph loop iteration counter when `should_skip` fires
- DO NOT add dependencies on Claude Code internals we can't control

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO formal test framework for hooks
- **Automated tests**: None (hooks are stdin/stdout scripts)
- **Framework**: N/A
- **Verification method**: Piped JSON → hook script → assert exit code + stdout

### QA Policy
Every task MUST include agent-executed QA scenarios using `Bash` (piped JSON to hook scripts).
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Hook testing**: Bash — pipe JSON payloads to hook scripts, assert exit codes and stdout
- **Settings changes**: Bash — parse JSON with jq/python, assert structure
- **Integration**: Bash — trigger actual stop hook chain with known state

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — independent fixes + state improvements):
├── Task 1: Add should_skip_stop_hooks() to test-validator.py [quick]
├── Task 2: Remove dead Guard 3 code from _common.py [quick]
├── Task 3: Enhance .stop-block-tracker.json with session_id + reason [quick]
├── Task 7: Add diagnostic logging for empirical validation [quick]
├── Task 8: Expand pre-compact.py to capture ralph-loop + richer state [quick]
├── Task 9: Raise handoff truncation limit + improve structure [quick]
└── Task 10: Improve session-start.py handoff injection [quick]

Wave 2 (After Wave 1 — core consolidation):
├── Task 4: Update Guard 5 to check block reason [unspecified-high] (depends: 3)
├── Task 5: Absorb quality-gate.py logic into stop_dispatcher.py [unspecified-high] (depends: 2)
└── Task 6: Consolidate 3 Stop hook groups → 1 in settings [unspecified-high] (depends: 1, 5)

Wave 3 (After Wave 2 — proactive detection):
├── Task 11: Add context pressure estimation to prompt-enhancer.py [deep] (depends: 3)
├── Task 12: Planning gate demotes to advisory under pressure [quick] (depends: 4)
└── Task 13: quality-runner short-circuits subprocess under pressure [quick] (depends: 4)

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Deadlock scenario QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → Task 6 (consolidation) → Task 11 (proactive) → F1-F4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 7 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 6 | 1 |
| 2 | — | 5 | 1 |
| 3 | — | 4, 11 | 1 |
| 7 | — | — | 1 |
| 8 | — | — | 1 |
| 9 | — | 10 | 1 |
| 10 | 9 | — | 1 |
| 4 | 3 | 12, 13 | 2 |
| 5 | 2 | 6 | 2 |
| 6 | 1, 5 | — | 2 |
| 11 | 3 | — | 3 |
| 12 | 4 | — | 3 |
| 13 | 4 | — | 3 |
| F1-F4 | ALL | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **7 tasks** — T1-T3,T7 → `quick`, T8-T10 → `quick`
- **Wave 2**: **3 tasks** — T4 → `unspecified-high`, T5 → `unspecified-high`, T6 → `unspecified-high`
- **Wave 3**: **3 tasks** — T11 → `deep`, T12 → `quick`, T13 → `quick`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Add `should_skip_stop_hooks()` guard to `test-validator.py`

  **What to do**:
  - Import `should_skip_stop_hooks` from `_common` (line 17, alongside existing `_resolve_project_dir` import)
  - Add the guard check immediately after `data = json.load(sys.stdin)` (after line 22)
  - Pattern: `if should_skip_stop_hooks(data): sys.exit(0)` — identical to quality-runner.py line 24
  - Verify NO other logic changes — only add the import and guard

  **Must NOT do**:
  - Do NOT modify any test validation logic
  - Do NOT change the import structure beyond adding `should_skip_stop_hooks`
  - Do NOT add any other guards or early exits

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-file, 3-line change, exact pattern exists in quality-runner.py
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `coding-standards`: Not needed — trivial patch matching existing pattern

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 7, 8, 9, 10)
  - **Blocks**: Task 6 (consolidation needs all hooks consistent)
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/quality-runner.py:15-25` — Exact pattern to copy: `from _common import ..., should_skip_stop_hooks` then `if should_skip_stop_hooks(data): sys.exit(0)`
  - `hooks/test-validator.py:17-22` — Current import and data loading code to patch

  **WHY Each Reference Matters**:
  - quality-runner.py shows the EXACT 3-line pattern (import, call, exit) that works. Copy it verbatim.
  - test-validator.py shows WHERE to insert: import goes on line 17, guard goes after line 22

  **Acceptance Criteria**:
  - [x] `from _common import _resolve_project_dir, should_skip_stop_hooks` on line 17 (or equivalent)
  - [x] `if should_skip_stop_hooks(data): sys.exit(0)` after data loading
  - [x] `python3 -m py_compile hooks/test-validator.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: stop_hook_active=true causes immediate exit (happy path)
    Tool: Bash
    Preconditions: hooks/ directory accessible, _common.py present
    Steps:
      1. Run: echo '{"stop_hook_active":true,"transcript_path":"/dev/null"}' | python3 hooks/test-validator.py
      2. Capture exit code: echo $?
      3. Capture stdout (should be empty)
    Expected Result: Exit code 0, no JSON output (hook skipped entirely)
    Failure Indicators: Non-zero exit code, or JSON output containing "decision":"block"
    Evidence: .sisyphus/evidence/task-1-skip-on-active.txt

  Scenario: Normal stop still validates tests (non-context-limit)
    Tool: Bash
    Preconditions: Create a fake test file with `assert True` in git diff
    Steps:
      1. Create temp test file: echo 'assert True' > /tmp/test_fake.test.py
      2. Run: echo '{"stop_hook_active":false,"transcript_path":"/dev/null"}' | python3 hooks/test-validator.py
      3. Capture exit code and stdout
    Expected Result: Exit code 0 (may or may not block depending on git state, but doesn't crash)
    Failure Indicators: Non-zero exit code from Python error, stack trace in stderr
    Evidence: .sisyphus/evidence/task-1-normal-stop-works.txt
  ```

  **Commit**: YES
  - Message: `fix(hooks): add should_skip guard to test-validator.py`
  - Files: `hooks/test-validator.py`
  - Pre-commit: `python3 -m py_compile hooks/test-validator.py`

- [x] 2. Remove dead Guard 3 code from `_common.py`

  **What to do**:
  - In `hooks/_common.py`, locate Guard 3 (lines ~276-298): the `_CONTEXT_PATTERNS` and `_RATE_LIMIT_PATTERNS` lists and the loop that checks `stop_reason`/`end_turn_reason`
  - Remove the entire Guard 3 block: the two pattern lists + the for loop that checks them
  - Keep the comment header but update it to explain WHY it was removed: `# Guard 3: REMOVED — stop_reason/end_turn_reason fields do not exist in Stop hook payloads`
  - Also remove the `stop_reason` and `end_turn_reason` variable assignments (lines ~282-283) IF they are ONLY used by Guard 3. Check that Guard 5 (line ~346) also uses them — if so, keep the assignments
  - Verify Guard 5 still works after Guard 3 removal

  **Must NOT do**:
  - Do NOT remove Guards 1, 2, 4, or 5
  - Do NOT change the `should_skip_stop_hooks()` function signature
  - Do NOT remove the diagnostic logging block (lines ~259-266)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-file cleanup, removing dead code, exact line numbers known
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 7, 8, 9, 10)
  - **Blocks**: Task 5 (quality-gate absorption depends on clean dispatcher)
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/_common.py:275-298` — Guard 3 dead code to remove (context patterns + rate limit patterns + for loop)
  - `hooks/_common.py:346` — Guard 5 uses `stop_reason` and `end_turn_reason` — KEEP these variable assignments
  - `hooks/_common.py:282-283` — Variable assignments for stop_reason/end_turn_reason — keep if Guard 5 needs them

  **WHY Each Reference Matters**:
  - Lines 275-298 are the dead code: `stop_reason`/`end_turn_reason` fields don't exist in Stop hook payloads (confirmed by Metis). The 15+ patterns checked here NEVER match.
  - Line 346 shows Guard 5 also reads `stop_reason`/`end_turn_reason` — the variable assignments must be preserved even though Guard 3's pattern matching is removed.

  **Acceptance Criteria**:
  - [x] `_CONTEXT_PATTERNS` and `_RATE_LIMIT_PATTERNS` lists removed
  - [x] Guard 3 for loop removed
  - [x] Comment explaining removal reason present
  - [x] Guard 5 still functions (stop_reason/end_turn_reason vars preserved)
  - [x] `python3 -m py_compile hooks/_common.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Guards 1,2,4,5 still work after Guard 3 removal
    Tool: Bash
    Preconditions: _common.py modified, .oal/state/ledger/ exists
    Steps:
      1. Run: python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import should_skip_stop_hooks; print(should_skip_stop_hooks({'stop_hook_active':True}))"
      2. Assert output is: True (Guard 1 works)
      3. Run: python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import should_skip_stop_hooks; print(should_skip_stop_hooks({'stop_hook_active':False}))"
      4. Assert output is: False (normal stop proceeds)
    Expected Result: Guard 1 returns True when stop_hook_active=True, False otherwise
    Failure Indicators: ImportError, AttributeError, or wrong boolean values
    Evidence: .sisyphus/evidence/task-2-guards-intact.txt

  Scenario: _CONTEXT_PATTERNS and _RATE_LIMIT_PATTERNS no longer exist
    Tool: Bash
    Preconditions: _common.py modified
    Steps:
      1. Run: grep -c '_CONTEXT_PATTERNS\|_RATE_LIMIT_PATTERNS' hooks/_common.py
      2. Assert count is 0 (or only in comments)
    Expected Result: No active code references to these pattern lists
    Failure Indicators: grep finds active (non-comment) references
    Evidence: .sisyphus/evidence/task-2-dead-code-removed.txt
  ```

  **Commit**: YES (groups with Task 1)
  - Message: `fix(hooks): add should_skip guard to test-validator and remove dead Guard 3`
  - Files: `hooks/_common.py`, `hooks/test-validator.py`
  - Pre-commit: `python3 -m py_compile hooks/_common.py hooks/test-validator.py`

- [x] 3. Enhance `.stop-block-tracker.json` with `session_id` and `reason`

  **What to do**:
  - In `hooks/_common.py`, modify `record_stop_block()` (line ~364):
    - Accept new parameter `reason: str = "unknown"` 
    - Read `session_id` from the Stop hook payload data (pass through from caller)
    - Write to tracker: `{"ts": ..., "count": ..., "session_id": "...", "reason": "..."}`
  - Modify `is_stop_block_loop()` (line ~385):
    - Read `session_id` from tracker, compare to current session
    - Only return True if `session_id` matches (prevent cross-session interference)
    - If no `session_id` in tracker (old format), fall back to current behavior
  - Update ALL callers of `record_stop_block()` in `stop_dispatcher.py` (lines ~680, ~686, ~713):
    - Pass `reason="planning_gate"`, `reason="ralph_loop"`, `reason="quality_check"` respectively
  - Update `record_stop_block()` in `_common.py:block_decision()` (line ~56):
    - This call has no data context — keep `reason="block_decision"` as default

  **Must NOT do**:
  - Do NOT change the `_BLOCK_LOOP_THRESHOLD` or `_BLOCK_LOOP_WINDOW_SECS` constants
  - Do NOT modify `reset_stop_block_tracker()`
  - Do NOT break backward compatibility with old tracker format (graceful fallback)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-file changes with clear pattern, adding fields to JSON
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 7, 8, 9, 10)
  - **Blocks**: Task 4 (Guard 5 update needs new tracker format), Task 11 (pressure detection reads tracker)
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/_common.py:364-382` — `record_stop_block()` function to modify (add session_id + reason params)
  - `hooks/_common.py:385-404` — `is_stop_block_loop()` function to modify (add session_id check)
  - `hooks/_common.py:46-58` — `block_decision()` calls `record_stop_block()` without data context
  - `hooks/stop_dispatcher.py:680-687` — Ralph loop and planning gate callers of `record_stop_block()`
  - `hooks/stop_dispatcher.py:713` — Quality check caller of `record_stop_block()`

  **WHY Each Reference Matters**:
  - _common.py:364-382 is where the tracker JSON is written — add session_id and reason fields here
  - _common.py:385-404 is where the tracker is READ — must compare session_id to prevent cross-session false positives
  - stop_dispatcher.py callers must pass meaningful reason strings for Guard 5 discrimination

  **Acceptance Criteria**:
  - [x] `record_stop_block()` accepts `reason` and `session_id` parameters
  - [x] `.stop-block-tracker.json` includes `session_id` and `reason` fields
  - [x] `is_stop_block_loop()` checks `session_id` match
  - [x] Old format tracker files (without session_id) don't crash — graceful fallback
  - [x] `python3 -m py_compile hooks/_common.py hooks/stop_dispatcher.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Tracker includes session_id and reason after block
    Tool: Bash
    Preconditions: Clean .oal/state/ledger/ directory
    Steps:
      1. Run: python3 -c "
         import sys; sys.path.insert(0,'hooks')
         from _common import record_stop_block
         record_stop_block(reason='planning_gate', session_id='test-session-123')
         import json; d=json.load(open('.oal/state/ledger/.stop-block-tracker.json'))
         print(d.get('session_id'), d.get('reason'))"
      2. Assert output contains: test-session-123 planning_gate
    Expected Result: Both session_id and reason are persisted in tracker JSON
    Failure Indicators: KeyError, missing fields, or wrong values
    Evidence: .sisyphus/evidence/task-3-tracker-fields.txt

  Scenario: Cross-session tracker doesn't trigger loop detection
    Tool: Bash
    Preconditions: Tracker exists with different session_id
    Steps:
      1. Write tracker with session_id='old-session': python3 -c "
         import json,os;from datetime import datetime,timezone
         os.makedirs('.oal/state/ledger',exist_ok=True)
         json.dump({'ts':datetime.now(timezone.utc).isoformat(),'count':5,'session_id':'old-session','reason':'loop'},
                   open('.oal/state/ledger/.stop-block-tracker.json','w'))"
      2. Run: python3 -c "
         import sys; sys.path.insert(0,'hooks')
         from _common import is_stop_block_loop
         print(is_stop_block_loop())"
      3. Assert output is: False (different session, not a loop)
    Expected Result: False — old session's blocks don't affect new session
    Failure Indicators: True (cross-session interference)
    Evidence: .sisyphus/evidence/task-3-session-isolation.txt
  ```

  **Commit**: YES
  - Message: `fix(hooks): enhance stop-block tracker with session_id and reason`
  - Files: `hooks/_common.py`, `hooks/stop_dispatcher.py`
  - Pre-commit: `python3 -m py_compile hooks/_common.py hooks/stop_dispatcher.py`

- [x] 7. Add diagnostic logging for empirical validation

  **What to do**:
  - In `hooks/stop_dispatcher.py` `main()` function (after line ~672), log the FULL hook payload to stderr:
    - `print(f"[OAL stop_dispatcher] payload keys: {list(data.keys())}", file=sys.stderr)`
    - `print(f"[OAL stop_dispatcher] stop_hook_active={data.get('stop_hook_active')}", file=sys.stderr)`
  - In `hooks/_common.py` `should_skip_stop_hooks()`, enhance existing diagnostic (line ~260-266):
    - Log which guard triggered: `print(f"[OAL] Guard N triggered: {reason}", file=sys.stderr)` for each guard
    - Log when NO guard triggers: `print(f"[OAL] All guards passed, hooks will run", file=sys.stderr)`
  - In `hooks/test-validator.py`, add similar diagnostic after should_skip check:
    - `print(f"[OAL test-validator] running, stop_hook_active={data.get('stop_hook_active')}", file=sys.stderr)`

  **Must NOT do**:
  - Do NOT log to stdout (that's the JSON decision channel)
  - Do NOT log sensitive data (transcript content, file contents)
  - Do NOT add logging that significantly slows hook execution

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Adding print statements to stderr, trivial changes
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 8, 9, 10)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/_common.py:259-266` — Existing diagnostic logging block to enhance
  - `hooks/_common.py:339` — Guard 4 logging pattern: `print(f"[OAL] Guard 4 triggered: ...", file=sys.stderr)`
  - `hooks/stop_dispatcher.py:668-672` — Entry point where payload logging goes

  **WHY Each Reference Matters**:
  - Existing diagnostic pattern shows the format to follow (stderr, [OAL] prefix)
  - Entry point in stop_dispatcher shows WHERE to add payload logging

  **Acceptance Criteria**:
  - [x] `stop_dispatcher.py` logs payload keys and stop_hook_active to stderr
  - [x] `_common.py` logs which guard triggered (or "all guards passed")
  - [x] NO logging goes to stdout
  - [x] `python3 -m py_compile hooks/stop_dispatcher.py hooks/_common.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Diagnostic logging appears on stderr
    Tool: Bash
    Preconditions: Modified hooks in place
    Steps:
      1. Run: echo '{"stop_hook_active":true,"transcript_path":"/dev/null"}' | python3 hooks/stop_dispatcher.py 2>/tmp/oal-diag.txt
      2. Read: cat /tmp/oal-diag.txt
      3. Assert contains: "[OAL" and "stop_hook_active"
    Expected Result: Diagnostic messages appear in stderr, nothing in stdout
    Failure Indicators: No output in stderr, or output appears in stdout
    Evidence: .sisyphus/evidence/task-7-diagnostic-logging.txt
  ```

  **Commit**: YES (groups with Task 3)
  - Message: `fix(hooks): enhance stop-block tracker with session_id and reason`
  - Files: `hooks/_common.py`, `hooks/stop_dispatcher.py`, `hooks/test-validator.py`
  - Pre-commit: `python3 -m py_compile hooks/_common.py hooks/stop_dispatcher.py hooks/test-validator.py`

- [x] 8. Expand `pre-compact.py` to capture ralph-loop state and richer failure context

  **What to do**:
  - Add `ralph-loop.json` to the `snapshot_files` list (line ~44-52):
    - `resolve_state_file(project_dir, "state/ralph-loop.json", "ralph-loop.json")`
  - Read ralph-loop state and include it in handoff parts (after line ~65):
    - Read `ralph-loop.json`, extract `active`, `iteration`, `max_iterations`, `original_prompt`
    - Add to parts: `## Ralph Loop\nIteration: {iter}/{max} | Goal: {original_prompt}`
  - Enhance failure tracker section (lines ~85-93):
    - Include the actual approach description, not just count
    - Format: `- {approach}: tried {count}x — {last_error_summary}` (up to 5 entries)
  - Add current Sisyphus plan context (if `.sisyphus/plans/*.md` exists):
    - Read first 5 lines of the active plan for task context
    - Add to parts: `## Active Plan\n{first 5 lines}`

  **Must NOT do**:
  - Do NOT change the snapshot rotation logic (keep latest 5)
  - Do NOT remove any existing snapshot files from the list
  - Do NOT exceed the truncation limit (will be raised in Task 9)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-file additions following existing patterns in the file
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 7, 9, 10)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/pre-compact.py:44-52` — `snapshot_files` list to extend with ralph-loop.json
  - `hooks/pre-compact.py:61-65` — State reading pattern (profile, wm, plan, checklist, tracker)
  - `hooks/pre-compact.py:67-93` — Parts assembly pattern for handoff.md
  - `hooks/pre-compact.py:85-93` — Failure tracker section to enhance

  **WHY Each Reference Matters**:
  - Lines 44-52 show the exact pattern for adding files to snapshot: `resolve_state_file()` call
  - Lines 61-65 show how to read state files with `read_file()` helper
  - Lines 67-93 show how handoff parts are assembled — follow the same append pattern

  **Acceptance Criteria**:
  - [x] `ralph-loop.json` included in snapshot_files list
  - [x] Ralph loop state appears in handoff.md when active
  - [x] Failure tracker shows approach descriptions, not just counts
  - [x] `python3 -m py_compile hooks/pre-compact.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Ralph loop state captured in handoff
    Tool: Bash
    Preconditions: ralph-loop.json exists with active loop
    Steps:
      1. Setup: python3 -c "
         import json,os
         os.makedirs('.oal/state',exist_ok=True)
         json.dump({'active':True,'iteration':5,'max_iterations':50,'original_prompt':'fix all tests'},
                   open('.oal/state/ralph-loop.json','w'))"
      2. Run: echo '{}' | python3 hooks/pre-compact.py 2>/dev/null
      3. Read: cat .oal/state/handoff.md
      4. Assert contains: 'Ralph' and 'iteration' and 'fix all tests'
    Expected Result: Handoff includes Ralph loop state with iteration count and goal
    Failure Indicators: No Ralph section in handoff, or missing iteration details
    Evidence: .sisyphus/evidence/task-8-ralph-in-handoff.txt
  ```

  **Commit**: YES
  - Message: `feat(hooks): expand pre-compact state capture for ralph-loop and failures`
  - Files: `hooks/pre-compact.py`
  - Pre-commit: `python3 -m py_compile hooks/pre-compact.py`

- [x] 9. Raise handoff truncation limit and improve handoff structure

  **What to do**:
  - In `hooks/pre-compact.py`, raise the handoff truncation limit from 60 lines to 120 lines (line ~112-113)
  - Raise the portable handoff limit from 100 lines to 150 lines (line ~121-122)
  - Restructure the handoff format for better post-compaction parsing:
    - Add a structured header: `## Resume Instructions\nRead .oal/state/profile.yaml + this file.`
    - Add section markers: `<!-- section: working-state -->`, `<!-- section: progress -->`
    - These markers help session-start.py parse the handoff more reliably
  - Keep the handoff as markdown (not JSON) for human readability

  **Must NOT do**:
  - Do NOT make handoff exceed 200 lines (context budget)
  - Do NOT change the handoff file path (`.oal/state/handoff.md`)
  - Do NOT change the portable handoff path

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Changing two numeric constants and adding a few structural lines
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 7, 8, 10)
  - **Blocks**: Task 10 (session-start needs to know the new structure)
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/pre-compact.py:112-113` — `if len(handoff_lines) > 60:` → change to 120
  - `hooks/pre-compact.py:121-122` — `if len(portable_lines) > 100:` → change to 150
  - `hooks/pre-compact.py:67-70` — Header/parts assembly where section markers should be added

  **Acceptance Criteria**:
  - [x] Handoff truncation at 120 lines (not 60)
  - [x] Portable truncation at 150 lines (not 100)
  - [x] Section markers present in output
  - [x] `python3 -m py_compile hooks/pre-compact.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Handoff allows 120 lines without truncation
    Tool: Bash
    Preconditions: State files with enough content to generate 80+ line handoff
    Steps:
      1. Setup: Create a large _checklist.md with 40 items
      2. Run: echo '{}' | python3 hooks/pre-compact.py 2>/dev/null
      3. Count lines: wc -l < .oal/state/handoff.md
      4. Assert: line count > 60 (would have been truncated before)
    Expected Result: Handoff has more than 60 lines when content warrants it
    Failure Indicators: Still truncated at 60 lines
    Evidence: .sisyphus/evidence/task-9-truncation-raised.txt
  ```

  **Commit**: YES (groups with Task 8)
  - Message: `feat(hooks): expand pre-compact state capture for ralph-loop and failures`
  - Files: `hooks/pre-compact.py`
  - Pre-commit: `python3 -m py_compile hooks/pre-compact.py`

- [x] 10. Improve `session-start.py` handoff injection

  **What to do**:
  - In `hooks/session-start.py`, enhance the handoff detection and injection:
    - Check for `.oal/state/handoff.md` existence (current behavior — verify it works)
    - If handoff exists, inject its FULL content (not truncated) into the session start context
    - Add clear marker: `[HANDOFF CONTEXT — Resume from previous session]`
    - After injection, rename handoff.md to handoff.md.consumed (prevent re-injection)
  - Ensure the injected context includes the `Resume Instructions` section from Task 9

  **Must NOT do**:
  - Do NOT delete handoff.md (rename to .consumed for debugging)
  - Do NOT inject handoff if `.consumed` version already exists (idempotent)
  - Do NOT exceed session_start_max_chars budget (2000 chars from settings.json)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-file changes to injection logic, following existing patterns
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (but should be after Task 9)
  - **Parallel Group**: Wave 1 (can start after Task 9 in same wave)
  - **Blocks**: None
  - **Blocked By**: Task 9 (needs to know new handoff structure)

  **References**:
  **Pattern References**:
  - `hooks/session-start.py` — Full file, find handoff injection logic
  - `hooks/_budget.py` — Session start max chars constant
  - `settings.json:197` — `session_start_max_chars: 2000`

  **WHY Each Reference Matters**:
  - session-start.py is where handoff gets injected into context — must find and modify injection point
  - Budget constants determine max injection size — handoff must fit within 2000 chars

  **Acceptance Criteria**:
  - [x] Handoff.md content injected with `[HANDOFF CONTEXT]` marker
  - [x] Handoff.md renamed to .consumed after injection
  - [x] Re-injection prevented if .consumed exists
  - [x] Injection respects session_start_max_chars budget
  - [x] `python3 -m py_compile hooks/session-start.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Handoff injected and consumed on session start
    Tool: Bash
    Preconditions: handoff.md exists from pre-compact
    Steps:
      1. Setup: echo '## Resume\nTest handoff content' > .oal/state/handoff.md
      2. Run: echo '{}' | python3 hooks/session-start.py 2>/dev/null
      3. Assert: .oal/state/handoff.md.consumed exists
      4. Assert: .oal/state/handoff.md does NOT exist
    Expected Result: Handoff consumed after injection
    Failure Indicators: Both files exist, or neither consumed
    Evidence: .sisyphus/evidence/task-10-handoff-consumed.txt
  ```

  **Commit**: YES (groups with Tasks 8, 9)
  - Message: `feat(hooks): expand pre-compact state capture for ralph-loop and failures`
  - Files: `hooks/session-start.py`
  - Pre-commit: `python3 -m py_compile hooks/session-start.py`

- [x] 4. Update Guard 5 to check block reason (prevent false positives)

  **What to do**:
  - In `hooks/_common.py`, modify Guard 5 (lines ~342-358):
    - Currently: `if not stop_reason and not end_turn_reason:` + check count >= 1
    - New logic: Check the `reason` field in `.stop-block-tracker.json`
    - Only skip hooks if the previous block's reason indicates a LOOP scenario (e.g., `"planning_gate"`, `"ralph_loop"`, `"quality_check"`), NOT a legitimate one-time quality block
    - Add a `_LOOP_BLOCK_REASONS` set: `{"planning_gate", "ralph_loop", "quality_check", "block_decision", "unknown"}`
    - Guard 5 condition: `count >= 1 AND reason in _LOOP_BLOCK_REASONS AND elapsed < window`
  - This prevents the false positive: legitimate quality block + quick normal stop skipping all gates

  **Must NOT do**:
  - Do NOT modify Guards 1, 2, or 4
  - Do NOT change the window or threshold constants
  - Do NOT break backward compatibility (old tracker without reason field = assume loop)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Logic change with subtle correctness requirements, needs careful reasoning
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6)
  - **Blocks**: Task 12 (planning gate advisory needs updated guard), Task 13
  - **Blocked By**: Task 3 (needs tracker with reason field)

  **References**:
  **Pattern References**:
  - `hooks/_common.py:342-358` — Current Guard 5 implementation to modify
  - `hooks/_common.py:385-404` — `is_stop_block_loop()` for context on how tracker is read
  - `hooks/_common.py:369` — Tracker JSON format: `{"ts": ..., "count": ..., "session_id": ..., "reason": ...}` (after Task 3)

  **WHY Each Reference Matters**:
  - Lines 342-358 are the exact code to modify — the empty stop_reason check needs to become a reason-aware check
  - Lines 385-404 show how the tracker is read elsewhere — must stay consistent

  **Acceptance Criteria**:
  - [x] Guard 5 checks `reason` field from tracker (not just count)
  - [x] `_LOOP_BLOCK_REASONS` set defined
  - [x] Old tracker format (no reason) treated as loop (backward compatible)
  - [x] `python3 -m py_compile hooks/_common.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Guard 5 skips on planning_gate reason (loop)
    Tool: Bash
    Preconditions: Tracker with reason='planning_gate', count=1, recent timestamp
    Steps:
      1. Setup tracker: python3 -c "
         import json,os;from datetime import datetime,timezone
         os.makedirs('.oal/state/ledger',exist_ok=True)
         json.dump({'ts':datetime.now(timezone.utc).isoformat(),'count':1,'reason':'planning_gate','session_id':'test'},
                   open('.oal/state/ledger/.stop-block-tracker.json','w'))"
      2. Run: python3 -c "
         import sys; sys.path.insert(0,'hooks')
         from _common import should_skip_stop_hooks
         print(should_skip_stop_hooks({'stop_hook_active':False}))"
      3. Assert output: True (Guard 5 skips on loop reason)
    Expected Result: True — planning_gate is a known loop reason
    Failure Indicators: False — Guard 5 not recognizing the reason
    Evidence: .sisyphus/evidence/task-4-guard5-loop-reason.txt
  ```

  **Commit**: YES
  - Message: `fix(hooks): update Guard 5 to check block reason for false positive prevention`
  - Files: `hooks/_common.py`
  - Pre-commit: `python3 -m py_compile hooks/_common.py`

- [x] 5. Absorb `quality-gate.py` logic into `stop_dispatcher.py`

  **What to do**:
  - Read `~/.claude/hooks/quality-gate.py` (102 lines) and understand its logic:
    - Detects bare "done" responses without structured completion reports
    - Checks transcript for last assistant message
    - Matches against `BARE_DONE_PATTERNS` and `COMPLETION_KEYWORDS`
    - Checks for `HAS_REPORT_MARKERS` (markdown headers, tables, etc.)
    - Blocks if bare done + no report markers
  - Create new check function `check_bare_done(data, project_dir)` in `stop_dispatcher.py`:
    - Add it as a new check in the `main()` function's check list (after check_write_failures)
    - Gate on feature flag: `if not get_feature_flag("bare_done", True): return []`
    - Move all the logic from quality-gate.py into this function
    - Use the `data.get("transcript_path")` already available in the payload
  - After absorption is verified, mark `~/.claude/hooks/quality-gate.py` for removal in Task 6

  **Must NOT do**:
  - Do NOT change the bare-done detection logic — preserve exact patterns and markers
  - Do NOT remove quality-gate.py yet (Task 6 handles settings consolidation)
  - Do NOT modify the block message wording

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Code migration between files, needs to preserve exact semantics
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 6)
  - **Blocks**: Task 6 (settings consolidation needs absorbed logic verified)
  - **Blocked By**: Task 2 (clean dispatcher without dead code)

  **References**:
  **Pattern References**:
  - `~/.claude/hooks/quality-gate.py:1-102` — Full source to absorb (bare-done detection logic)
  - `hooks/stop_dispatcher.py:693-700` — Check function list where `check_bare_done` should be added
  - `hooks/stop_dispatcher.py:412-444` — `check_false_fix()` — similar check pattern to follow

  **WHY Each Reference Matters**:
  - quality-gate.py is the complete source to migrate — copy logic verbatim then adapt to dispatcher pattern
  - The check function list in main() shows WHERE to register the new check
  - check_false_fix() is the closest analogy — similar structure, similar output format

  **Acceptance Criteria**:
  - [x] `check_bare_done()` function exists in stop_dispatcher.py
  - [x] Bare-done detection logic identical to quality-gate.py
  - [x] Feature flag `bare_done` controls it
  - [x] Registered in main() check list
  - [x] `python3 -m py_compile hooks/stop_dispatcher.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Bare 'done' response blocked by absorbed logic
    Tool: Bash
    Preconditions: Create transcript with bare 'done' assistant message
    Steps:
      1. Setup transcript: python3 -c "
         import json
         with open('/tmp/test-transcript.jsonl','w') as f:
           f.write(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'Done.'}]}})+'\n')"
      2. Clean tracker: rm -f .oal/state/ledger/.stop-block-tracker.json
      3. Run: echo '{"stop_hook_active":false,"transcript_path":"/tmp/test-transcript.jsonl"}' | python3 hooks/stop_dispatcher.py
      4. Assert stdout contains: '"decision":"block"' or '"decision": "block"'
    Expected Result: Block decision with reason about structured report
    Failure Indicators: No output (bare done not detected), or exit without blocking
    Evidence: .sisyphus/evidence/task-5-bare-done-blocked.txt

  Scenario: Proper completion report NOT blocked
    Tool: Bash
    Preconditions: Transcript with structured completion report
    Steps:
      1. Setup transcript: python3 -c "
         import json
         with open('/tmp/test-transcript-good.jsonl','w') as f:
           f.write(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'## Files Modified\n- src/auth.ts: Added JWT validation\n\n**Checks Run**: tsc exit 0, jest 42 passed\n\n**Confidence**: High'}]}})+'\n')"
      2. Clean tracker: rm -f .oal/state/ledger/.stop-block-tracker.json
      3. Run: echo '{"stop_hook_active":false,"transcript_path":"/tmp/test-transcript-good.jsonl"}' | python3 hooks/stop_dispatcher.py
      4. Assert stdout is empty OR doesn't contain 'bare' or 'done' block reason
    Expected Result: No block from bare-done check (proper report detected)
    Failure Indicators: Block decision with bare-done reason despite structured report
    Evidence: .sisyphus/evidence/task-5-proper-report-passes.txt
  ```

  **Commit**: YES
  - Message: `refactor(hooks): absorb quality-gate bare-done detection into stop_dispatcher`
  - Files: `hooks/stop_dispatcher.py`
  - Pre-commit: `python3 -m py_compile hooks/stop_dispatcher.py`

- [x] 6. Consolidate 3 Stop hook groups into 1 in `~/.claude/settings.json`

  **What to do**:
  - Modify `OAL-setup.sh` (or create a migration script) to consolidate Stop hooks:
    - Current 3 groups: quality-gate.py (group 1), test-validator.py + quality-runner.py (group 2), stop_dispatcher.py (group 3)
    - Target 1 group: ONLY stop_dispatcher.py (which now absorbs quality-gate logic from Task 5)
    - test-validator.py and quality-runner.py remain as separate files but are called FROM stop_dispatcher.py
  - **IMPORTANT — Python import caveat**: Hyphenated filenames (`test-validator.py`, `quality-runner.py`) are NOT directly importable as Python modules. Use one of:
    - `importlib.import_module()` with the hyphenated name
    - OR create thin underscore-named wrappers (e.g., `test_validator_lib.py`) that expose the check functions
    - OR use `subprocess.run(['python3', 'hooks/test-validator.py'], ...)` instead of Python import
  - Update `stop_dispatcher.py` to call test-validator and quality-runner checks:
    - Expose test validation logic as a callable function: `check_test_quality(data, project_dir)`
    - Expose quality runner logic as a callable function: `check_quality_runner(data, project_dir)`
    - Call these in the main() check list, wrapped in try/except for crash isolation
  - Remove `quality-gate.py` from `~/.claude/hooks/` (logic absorbed in Task 5)
  - Update `settings.json` Stop section to single entry: `[{"hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/stop_dispatcher.py", "timeout": 90}]}]`
  - Timeout raised to 90s to accommodate quality-runner's subprocess execution
  - Update `OAL-setup.sh` to handle this consolidation during install/update

  **Must NOT do**:
  - Do NOT delete test-validator.py or quality-runner.py source files (keep as importable modules)
  - Do NOT remove user-custom Stop hooks that aren't OAL hooks
  - Do NOT change the Stop hook timeout below 90s (quality-runner needs 60s for subprocess)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multi-file refactor involving settings merge, imports, and installer changes
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after Tasks 1, 5)
  - **Blocks**: None directly (Wave 3 can start after)
  - **Blocked By**: Task 1 (test-validator must have should_skip), Task 5 (quality-gate absorbed)

  **References**:
  **Pattern References**:
  - `~/.claude/settings.json` Stop section — Current 3-group structure to replace with 1 group
  - `hooks/stop_dispatcher.py:693-700` — Check function list where test-validator and quality-runner checks go
  - `hooks/test-validator.py:48-119` — Core validation logic to expose as importable function
  - `hooks/quality-runner.py:32-162` — Quality runner logic to expose as importable function
  - `OAL-setup.sh` — Installer that writes settings.json Stop hooks

  **WHY Each Reference Matters**:
  - Settings.json is the TARGET — 3 groups become 1
  - stop_dispatcher check list is where imported functions get registered
  - test-validator and quality-runner need to be refactored to expose callable functions
  - OAL-setup.sh must be updated to write the new consolidated structure

  **Acceptance Criteria**:
  - [x] `~/.claude/settings.json` has exactly 1 Stop hook group
  - [x] Stop hook points to `stop_dispatcher.py` with timeout 90s
  - [x] `quality-gate.py` removed from `~/.claude/hooks/`
  - [x] test-validator and quality-runner callable as functions from stop_dispatcher
  - [x] ALL existing checks still run during normal stops
  - [x] `python3 -m py_compile hooks/stop_dispatcher.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Single Stop hook group in settings
    Tool: Bash
    Preconditions: settings.json updated
    Steps:
      1. Run: python3 -c "import json;d=json.load(open('$HOME/.claude/settings.json'));print(len(d['hooks']['Stop']))"
      2. Assert output: 1
    Expected Result: Exactly 1 Stop hook group
    Failure Indicators: 2 or 3 (not consolidated)
    Evidence: .sisyphus/evidence/task-6-single-stop-group.txt

  Scenario: All checks still run on normal stop
    Tool: Bash
    Preconditions: Pending checklist, clean tracker
    Steps:
      1. Setup: echo '- [x] Pending task' > .oal/state/_checklist.md
      2. Clean: rm -f .oal/state/ledger/.stop-block-tracker.json
      3. Run: echo '{"stop_hook_active":false,"transcript_path":"/dev/null"}' | python3 hooks/stop_dispatcher.py
      4. Assert stdout contains: '"decision"' (some check should block)
    Expected Result: Planning gate blocks because of pending checklist
    Failure Indicators: No output (checks not running)
    Evidence: .sisyphus/evidence/task-6-all-checks-run.txt
  ```

  **Commit**: YES
  - Message: `refactor(hooks): consolidate 3 stop hook groups into single dispatcher`
  - Files: `hooks/stop_dispatcher.py`, `hooks/test-validator.py`, `hooks/quality-runner.py`, `~/.claude/settings.json`, `OAL-setup.sh`
  - Pre-commit: `python3 -m py_compile hooks/stop_dispatcher.py hooks/test-validator.py hooks/quality-runner.py`

- [x] 11. Add context pressure estimation to `prompt-enhancer.py`

  **What to do**:
  - In `hooks/prompt-enhancer.py`, add a context pressure estimation system:
    - Track tool call count per session using the tool-ledger.jsonl
    - Define threshold: `_CONTEXT_PRESSURE_THRESHOLD = 150` (tool calls)
    - When tool call count exceeds threshold, inject auto-handoff suggestion:
      - `@context-pressure: High context usage detected ({count} tool calls). Auto-saving state...`
    - Trigger auto-handoff: write a signal file `.oal/state/.auto-handoff-requested`
    - The signal file triggers stop_dispatcher to demote all blocking checks to advisory
  - Add a helper function `estimate_context_pressure(project_dir)` that returns `(tool_count, threshold, is_high)`
  - **IMPORTANT**: Since `prompt-enhancer.py` has a hyphen in the name, this function should be placed in a NEW file `hooks/context_pressure.py` (underscore name, importable) that both prompt-enhancer.py and stop_dispatcher.py can import from
  - Save the estimation to `.oal/state/.context-pressure.json`:
    - `{"tool_count": N, "threshold": 150, "is_high": true/false, "ts": "..."}`

  **Must NOT do**:
  - Do NOT auto-run `/compact` (can't invoke CLI commands from hooks)
  - Do NOT block user prompts based on pressure (advisory only)
  - Do NOT make the threshold non-configurable (read from settings.json `_oal.context_budget.pressure_threshold` if set)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: New feature requiring integration with ledger, pressure estimation logic, signal file coordination
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 12, 13)
  - **Blocks**: None
  - **Blocked By**: Task 3 (reads tracker format)

  **References**:
  **Pattern References**:
  - `hooks/prompt-enhancer.py` — Full file, find injection point for pressure hint
  - `hooks/tool-ledger.py` — Writes tool-ledger.jsonl entries that we count
  - `hooks/stop_dispatcher.py:132-197` — `_build_context()` shows how to read ledger entries (NOTE: this function is in stop_dispatcher.py, NOT _common.py)
  - `settings.json:196-200` — `context_budget` section for threshold configuration

  **WHY Each Reference Matters**:
  - prompt-enhancer is where the hint gets injected into user prompts
  - tool-ledger shows the format of entries we need to count
  - _build_context() already reads ledger entries — reuse the same pattern
  - settings.json context_budget already exists as config location for the threshold

  **Acceptance Criteria**:
  - [x] `estimate_context_pressure()` function exists and returns `(count, threshold, is_high)`
  - [x] `.context-pressure.json` written with current estimation
  - [x] Hint injected into prompt when threshold exceeded
  - [x] Threshold configurable via settings.json `pressure_threshold`
  - [x] `python3 -m py_compile hooks/prompt-enhancer.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: High pressure detected when tool count exceeds threshold
    Tool: Bash
    Preconditions: tool-ledger.jsonl with 160+ entries
    Steps:
      1. Setup: Generate 160 ledger entries: python3 -c "
         import json,os; from datetime import datetime,timezone
         os.makedirs('.oal/state/ledger',exist_ok=True)
         with open('.oal/state/ledger/tool-ledger.jsonl','w') as f:
           for i in range(160):
             f.write(json.dumps({'ts':datetime.now(timezone.utc).isoformat(),'tool':'Bash','command':'echo test'})+'\n')"
      2. Run: python3 -c "
         import sys; sys.path.insert(0,'hooks')
         from prompt_enhancer_helpers import estimate_context_pressure
         count,threshold,is_high = estimate_context_pressure('.')
         print(f'{count} {threshold} {is_high}')"
      3. Assert output: 160 150 True
    Expected Result: High pressure detected (160 > 150 threshold)
    Failure Indicators: is_high=False or ImportError
    Evidence: .sisyphus/evidence/task-11-pressure-detection.txt
  ```

  **Commit**: YES
  - Message: `feat(hooks): add proactive context pressure detection`
  - Files: `hooks/prompt-enhancer.py`
  - Pre-commit: `python3 -m py_compile hooks/prompt-enhancer.py`

- [x] 12. Planning gate demotes to advisory under context pressure

  **What to do**:
  - In `hooks/stop_dispatcher.py`, modify `check_planning_gate()` (line ~616-635):
    - Before blocking, check context pressure: read `.oal/state/.context-pressure.json`
    - If `is_high` is True, demote from block to advisory:
      - Instead of returning `[block_message]`, append to `data["_stop_advisories"]`
      - Return `[]` (no blocks)
    - Also check `is_stop_block_loop()` — if True, demote to advisory
  - The advisory still appears in stderr but doesn't prevent the stop

  **Must NOT do**:
  - Do NOT demote on first-attempt normal stops (only on confirmed pressure)
  - Do NOT remove the planning gate entirely
  - Do NOT change the advisory message content

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small logic change in one function, adding a conditional check
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 13)
  - **Blocks**: None
  - **Blocked By**: Task 4 (Guard 5 must be updated to provide context for pressure)

  **References**:
  **Pattern References**:
  - `hooks/stop_dispatcher.py:616-635` — `check_planning_gate()` to modify
  - `hooks/stop_dispatcher.py:673` — `data["_stop_advisories"]` pattern for advisory mode
  - `hooks/_common.py:385-404` — `is_stop_block_loop()` to check as additional demotion signal

  **Acceptance Criteria**:
  - [x] Planning gate returns advisory (not block) when `.context-pressure.json` shows `is_high: true`
  - [x] Planning gate still blocks on normal stops (pressure not high)
  - [x] `python3 -m py_compile hooks/stop_dispatcher.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Planning gate demotes to advisory under pressure
    Tool: Bash
    Preconditions: Pending checklist + high context pressure
    Steps:
      1. Setup checklist: echo '- [x] Pending task' > .oal/state/_checklist.md
      2. Setup pressure: python3 -c "
         import json,os; os.makedirs('.oal/state',exist_ok=True)
         json.dump({'tool_count':200,'threshold':150,'is_high':True},open('.oal/state/.context-pressure.json','w'))"
      3. Clean tracker: rm -f .oal/state/ledger/.stop-block-tracker.json
      4. Run: echo '{"stop_hook_active":false,"transcript_path":"/dev/null"}' | python3 hooks/stop_dispatcher.py 2>/tmp/oal-advisory.txt
      5. Check stdout: should be empty (no block)
      6. Check stderr: cat /tmp/oal-advisory.txt | grep -c 'Planning gate'
    Expected Result: No block in stdout, advisory in stderr mentioning planning gate
    Failure Indicators: Block decision in stdout despite high pressure
    Evidence: .sisyphus/evidence/task-12-planning-gate-advisory.txt
  ```

  **Commit**: YES (groups with Task 13)
  - Message: `feat(hooks): demote blocking checks to advisory under context pressure`
  - Files: `hooks/stop_dispatcher.py`
  - Pre-commit: `python3 -m py_compile hooks/stop_dispatcher.py`

- [x] 13. `quality-runner.py` short-circuits subprocess under context pressure

  **What to do**:
  - In `hooks/quality-runner.py`, after the `should_skip_stop_hooks()` check (line ~24):
    - Read `.oal/state/.context-pressure.json`
    - If `is_high` is True, skip all subprocess execution (format/lint/typecheck/test)
    - Log to stderr: `[OAL quality-runner] Skipping subprocess checks: context pressure high`
    - Still allow the hook to exit cleanly (exit 0)
  - Also check `is_stop_block_loop()` as an additional skip signal
  - This prevents wasting 60s on test suite execution when the system is trying to compact

  **Must NOT do**:
  - Do NOT remove the subprocess execution logic (only skip it conditionally)
  - Do NOT change the quality-gate.json parsing
  - Do NOT change the allowed command prefix whitelist

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Adding one conditional early-exit check, following existing skip pattern
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 12)
  - **Blocks**: None
  - **Blocked By**: Task 4 (consistent pressure detection approach)

  **References**:
  **Pattern References**:
  - `hooks/quality-runner.py:23-25` — Existing `should_skip_stop_hooks()` pattern to follow
  - `hooks/quality-runner.py:39-162` — Subprocess execution logic that gets skipped

  **Acceptance Criteria**:
  - [x] Subprocess execution skipped when `.context-pressure.json` shows `is_high: true`
  - [x] Log message indicates skip reason
  - [x] Normal stops still run subprocess checks
  - [x] `python3 -m py_compile hooks/quality-runner.py` → exit 0

  **QA Scenarios:**

  ```
  Scenario: Quality runner skips subprocess under pressure
    Tool: Bash
    Preconditions: quality-gate.json with test command + high pressure
    Steps:
      1. Setup: echo '{"test":"echo pass"}' > .oal/state/quality-gate.json
      2. Setup pressure: python3 -c "
         import json,os; os.makedirs('.oal/state',exist_ok=True)
         json.dump({'tool_count':200,'threshold':150,'is_high':True},open('.oal/state/.context-pressure.json','w'))"
      3. Run: echo '{"stop_hook_active":false,"transcript_path":"/dev/null"}' | python3 hooks/quality-runner.py 2>/tmp/oal-qr.txt
      4. Check stderr: cat /tmp/oal-qr.txt
      5. Assert contains: 'context pressure' or 'Skipping'
    Expected Result: Subprocess skipped with log message, clean exit
    Failure Indicators: Subprocess actually executed (no skip log)
    Evidence: .sisyphus/evidence/task-13-quality-runner-skip.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `feat(hooks): demote blocking checks to advisory under context pressure`
  - Files: `hooks/quality-runner.py`
  - Pre-commit: `python3 -m py_compile hooks/quality-runner.py`

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run `echo '{}' | python3 hooks/stop_dispatcher.py`). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m py_compile hooks/stop_dispatcher.py` + all modified hooks. Review all changed files for: bare excepts without pass, missing imports, unused variables, inconsistent error handling. Check for AI slop: excessive comments, over-abstraction, generic names.
  Output: `Compile [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Deadlock Scenario QA** — `unspecified-high` (+ deadlock simulation)
  Simulate the exact deadlock sequence: create a checklist with pending items, set up `ralph-loop.json` active, then pipe stop hook payloads with `stop_hook_active=false` followed by `stop_hook_active=true`. Verify: first attempt may block, second attempt MUST allow through. Verify quality gates still work on normal stops.
  Output: `Deadlock Prevention [PASS/FAIL] | Quality Gates [PASS/FAIL] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `fix(hooks): add should_skip guard to test-validator and remove dead Guard 3` — test-validator.py, _common.py
- **Wave 1**: `fix(hooks): enhance stop-block tracker with session_id and reason` — _common.py
- **Wave 1**: `feat(hooks): expand pre-compact state capture and handoff quality` — pre-compact.py, session-start.py
- **Wave 2**: `refactor(hooks): consolidate stop hooks and absorb quality-gate logic` — stop_dispatcher.py, quality-gate.py, settings merge
- **Wave 3**: `feat(hooks): add proactive context pressure detection` — prompt-enhancer.py, stop_dispatcher.py, quality-runner.py

---

## Success Criteria

### Verification Commands
```bash
# Deadlock prevention: stop_hook_active=true skips ALL hooks
echo '{"stop_hook_active":true,"transcript_path":"/dev/null"}' | python3 hooks/test-validator.py; echo "exit: $?"
# Expected: exit: 0 (no output, hook skipped)

echo '{"stop_hook_active":true,"transcript_path":"/dev/null"}' | python3 hooks/stop_dispatcher.py; echo "exit: $?"
# Expected: exit: 0 (no output, hook skipped)

# Quality gates still work on normal stops
echo '{"stop_hook_active":false,"transcript_path":"/dev/null"}' | python3 hooks/stop_dispatcher.py
# Expected: JSON with "decision":"block" if checklist has pending items

# Guard 4 loop breaker
python3 -c "import json,os;from datetime import datetime,timezone;os.makedirs('.oal/state/ledger',exist_ok=True);json.dump({'ts':datetime.now(timezone.utc).isoformat(),'count':3,'session_id':'test','reason':'loop'},open('.oal/state/ledger/.stop-block-tracker.json','w'))"
echo '{"stop_hook_active":false,"transcript_path":"/dev/null"}' | python3 hooks/stop_dispatcher.py; echo "exit: $?"
# Expected: exit: 0 (Guard 4 triggered)

# Single Stop hook group in settings
python3 -c "import json;d=json.load(open('$HOME/.claude/settings.json'));print(len(d['hooks']['Stop']))"
# Expected: 1
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All hooks compile: `python3 -m py_compile hooks/*.py`
- [x] Deadlock scenario passes
- [x] Quality gates still block on normal stops
