# OMG Code Review Remediation Plan

## TL;DR

> **Quick Summary**: Remediate 12 findings (3 P0, 1 P1, 8 P2) from the comprehensive OMG code review. Security-critical fixes first (secret scan signaling, pattern classification, exception handling), then observability improvements, then code quality polish.
> 
> **Deliverables**:
> - P0: Secret scan signal file mechanism, fixed NON_SOURCE_PATTERNS classification, hardened exception handlers in 4 security-critical files
> - P1: Audit logging before silent file deletions
> - P2: os.getcwd() validation helper, word-boundary matching, control plane warning, shutil.which caching, installer path assertions, knowledge index validation, deprecated API fix, duplicate comment removal
> 
> **Estimated Effort**: Medium (16 tasks + 4 verification)
> **Parallel Execution**: YES — 6 waves + FINAL
> **Critical Path**: T1 → T4/T5 → T7/T8 → FINAL

---

## Context

### Original Request
Comprehensive code review of the OMG repository identified 12 findings across P0/P1/P2 severity levels. User requested a prioritized remediation plan with exact file:line references, dependency ordering, and verification criteria.

### Interview Summary
**Key Discussions**:
- Metis identified that `exit(0)` and `except Exception: pass` are implementations of a documented **crash isolation policy**, not bugs
- User deferred crash isolation decision to Prometheus → **Signal file mechanism chosen** (preserves crash isolation, adds observability)
- Exception handler scope → **Security-critical only** (~12 handlers in 4 files: post-write.py, stop_dispatcher.py, config-guard.py, _common.py)
- F6 reclassified P1→P2 (redundant call, not duplicate definition), F5 reclassified P1→P2 (default is 127.0.0.1, not 0.0.0.0)

### Metis Review
**Identified Gaps** (addressed):
- Crash isolation vs. security blocking tension → Resolved: signal file mechanism
- F3 scope unbounded (41 handlers) → Resolved: security-critical only (~12)
- F6 false positive → Resolved: reclassified as P2 efficiency fix
- F5 severity overstatement → Resolved: downgraded to P2
- Overlapping findings (F4+F3 in pre-compact.py, F11+F3 in prompt-enhancer.py) → Handled in task ordering
- Korean tokenization in F8 → Word-boundary for Latin only, substring stays for Korean
- _common.py blast radius → setup_crash_handler() NOT modified without explicit approval

---

## Work Objectives

### Core Objective
Fix all 12 code review findings in priority order, preserving OMG's crash isolation architecture while adding security observability and reducing silent failure modes.

### Concrete Deliverables
- `hooks/post-write.py`: Signal file mechanism for secret detection, cleaned exception handlers, removed duplicate comment
- `hooks/stop_dispatcher.py`: Fixed NON_SOURCE_PATTERNS classification, cleaned exception handlers
- `hooks/config-guard.py`: Cleaned exception handlers
- `hooks/_common.py`: `_resolve_project_dir()` helper, cleaned critical-write exception handlers
- `hooks/pre-compact.py`: Audit logging before rmtree
- `hooks/shadow_manager.py`: Audit logging before rmtree
- `hooks/prompt-enhancer.py`: Word-boundary matching (Latin), knowledge index validation, deprecated utcnow fix
- `control_plane/server.py`: Stderr warning for --host 0.0.0.0
- `runtime/team_router.py`: Cached shutil.which result
- `OMG-setup.sh`: Path-prefix assertions for rm -rf
- Remaining hooks: _resolve_project_dir() applied

### Definition of Done
- [x] `python3 -m py_compile <file>` passes for every modified .py file
- [x] `ast-grep --pattern 'except Exception: pass' --lang python` returns 0 matches in security-critical files
- [x] `grep -r 'os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())' hooks/` returns 0 matches
- [x] All evidence files present in `.sisyphus/evidence/`

### Must Have
- Signal file mechanism for secret detection (`.omg/state/secret-detected.json`)
- Fixed NON_SOURCE_PATTERNS: hooks/ and scripts/ paths correctly classified as source
- Exception handlers in security paths log to stderr instead of silently passing
- Audit trail before every `shutil.rmtree` call
- `_resolve_project_dir()` helper used consistently across all hooks

### Must NOT Have (Guardrails)
- **G1**: DO NOT change `_common.py:setup_crash_handler()` — it's the outer safety net imported by every hook
- **G2**: DO NOT add any dependencies beyond Python stdlib — OMG is stdlib-only
- **G3**: DO NOT change hook stdin/stdout/stderr interface contract — Claude Code reads these
- **G4**: DO NOT refactor adjacent code "while in the file" — pure finding remediation only
- **G5**: DO NOT use `logging.getLogger` — hooks use `print(..., file=sys.stderr)` pattern
- **G6**: DO NOT add word-boundary regex to Korean signal tokens — Korean has no word boundaries, substring matching is correct
- **G7**: DO NOT change exit codes from 0 to non-zero — crash isolation policy preserved
- **G8**: DO NOT add interactive prompts to OMG-setup.sh — $DRY_RUN already mitigates
- **G9**: DO NOT add schema validation libraries (pydantic, jsonschema) for F10 — stdlib isinstance() only
- **G10**: Each task touches ≤3 files

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision
- **Infrastructure exists**: NO (no test framework detected)
- **Automated tests**: None — no jest/vitest/pytest/bun test
- **Framework**: None
- **Primary verification**: `python3 -m py_compile`, `ast-grep`, `grep`, file existence checks

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python hooks**: `python3 -m py_compile <file>` + `ast-grep` pattern verification
- **Shell scripts**: `bash -n <file>` syntax check + `grep` pattern verification
- **All files**: `grep`/`ast-grep` to verify old patterns removed and new patterns present

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — 3 parallel, independent):
├── T1: _common.py helper (_resolve_project_dir) [quick]
├── T2: post-write.py duplicate comment removal [quick]
└── T3: prompt-enhancer.py deprecated utcnow fix [quick]

Wave 2 (P0/P1 Core Security — 3 parallel, after Wave 1):
├── T4: post-write.py signal file mechanism (depends: T1, T2) [deep]
├── T5: stop_dispatcher.py NON_SOURCE_PATTERNS fix (depends: T1) [deep]
└── T6: pre-compact.py + shadow_manager.py audit logging (depends: T1) [unspecified-high]

Wave 3 (P0 Exception Handlers — 4 parallel, after Wave 2):
├── T7: post-write.py exception handlers (depends: T4) [unspecified-high]
├── T8: stop_dispatcher.py exception handlers (depends: T5) [unspecified-high]
├── T9: config-guard.py exception handlers [unspecified-high]
└── T10: _common.py critical-write exception handlers (depends: T1) [unspecified-high]

Wave 4 (P2 Independent — 4 parallel):
├── T11: prompt-enhancer.py word-boundary + knowledge index (depends: T3) [deep]
├── T12: server.py --host warning [quick]
├── T13: team_router.py cache shutil.which [quick]
└── T14: OMG-setup.sh path assertions [quick]

Wave 5 (Sweep — 1 task):
└── T15: Apply _resolve_project_dir() to remaining hooks [unspecified-high]

Wave FINAL (Verification — 4 parallel):
├── F1: Plan compliance audit [oracle]
├── F2: Code quality review [unspecified-high]
├── F3: Real QA — pattern verification [unspecified-high]
└── F4: Scope fidelity check [deep]

Critical Path: T1 → T4 → T7 → FINAL
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Waves 3, 4, FINAL)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T4, T5, T6, T10, T15 | 1 |
| T2 | — | T4 | 1 |
| T3 | — | T11 | 1 |
| T4 | T1, T2 | T7 | 2 |
| T5 | T1 | T8 | 2 |
| T6 | T1 | — | 2 |
| T7 | T4 | — | 3 |
| T8 | T5 | — | 3 |
| T9 | — | — | 3 |
| T10 | T1 | — | 3 |
| T11 | T3 | — | 4 |
| T12 | — | — | 4 |
| T13 | — | — | 4 |
| T14 | — | — | 4 |
| T15 | T1, T4-T11 | — | 5 |
| F1-F4 | ALL | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 3 — T1→`quick`, T2→`quick`, T3→`quick`
- **Wave 2**: 3 — T4→`deep`, T5→`deep`, T6→`unspecified-high`
- **Wave 3**: 4 — T7-T10→`unspecified-high`
- **Wave 4**: 4 — T11→`deep`, T12-T14→`quick`
- **Wave 5**: 1 — T15→`unspecified-high`
- **FINAL**: 4 — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [x] 1. Add `_resolve_project_dir()` helper to `hooks/_common.py` (F7 Foundation)

  **What to do**:
  - Add a new function `_resolve_project_dir()` to `hooks/_common.py` that:
    1. Reads `os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())`
    2. Validates the resolved path contains `.omg/` directory (or creates it if missing)
    3. Returns the validated path
    4. Falls back gracefully if validation fails (returns the path with stderr warning)
  - Place the function near the top of the file, after imports
  - Do NOT modify `setup_crash_handler()` or any existing function

  **Must NOT do**:
  - DO NOT modify `setup_crash_handler()` — highest blast radius function
  - DO NOT add any imports beyond stdlib
  - DO NOT change any existing function signatures

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single function addition to one file, straightforward stdlib Python
  - **Skills**: []
    - No specialized skills needed for stdlib Python helper function

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3)
  - **Blocks**: T4, T5, T6, T10, T15
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `hooks/_common.py:1-50` — Import section and existing helper functions (follow same style)
  - `hooks/_common.py:setup_crash_handler()` — DO NOT TOUCH, but read to understand the crash isolation pattern

  **API/Type References**:
  - `os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())` — The exact pattern being replaced (search hooks/ for all occurrences)

  **WHY Each Reference Matters**:
  - `_common.py` top section shows the coding style (no docstrings, terse, stderr for logging)
  - The `os.environ.get` pattern tells you exactly what the helper must replicate + improve

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/_common.py` → exit 0
  - [x] `grep '_resolve_project_dir' hooks/_common.py` → function definition found
  - [x] `grep 'setup_crash_handler' hooks/_common.py` → unchanged from original

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Helper function exists and compiles
    Tool: Bash
    Preconditions: hooks/_common.py modified with new function
    Steps:
      1. Run `python3 -m py_compile hooks/_common.py`
      2. Run `grep -n 'def _resolve_project_dir' hooks/_common.py`
      3. Run `python3 -c "from hooks._common import _resolve_project_dir; print('OK')"` (may fail due to stdin, so use py_compile as primary)
    Expected Result: py_compile exits 0, grep shows function definition with line number
    Failure Indicators: py_compile exits non-zero, or grep returns no matches
    Evidence: .sisyphus/evidence/task-1-helper-exists.txt

  Scenario: setup_crash_handler unchanged
    Tool: Bash
    Preconditions: hooks/_common.py modified
    Steps:
      1. Run `git diff hooks/_common.py`
      2. Verify diff does NOT contain changes to setup_crash_handler
      3. Run `grep -A5 'def setup_crash_handler' hooks/_common.py` and compare to original
    Expected Result: setup_crash_handler function body identical to pre-change
    Failure Indicators: git diff shows modifications inside setup_crash_handler
    Evidence: .sisyphus/evidence/task-1-no-crash-handler-change.txt
  ```

  **Commit**: YES — group with Wave 1
  - Message: `fix(hooks): add _resolve_project_dir helper to _common.py`
  - Files: `hooks/_common.py`
  - Pre-commit: `python3 -m py_compile hooks/_common.py`

- [x] 2. Remove duplicate comment in `hooks/post-write.py` (F12)

  **What to do**:
  - Remove the duplicate comment at `hooks/post-write.py:29-30` — lines 29 and 30 contain the identical comment
  - Delete one of the two identical lines

  **Must NOT do**:
  - DO NOT change any other code in the file
  - DO NOT modify the secret detection logic

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-line deletion, trivial change
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3)
  - **Blocks**: T4
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/post-write.py:28-32` — The duplicate comment area. Lines 29 and 30 are identical.

  **WHY Each Reference Matters**:
  - Read lines 28-32 to confirm which line to delete (keep the first, remove the second)

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/post-write.py` → exit 0
  - [x] No consecutive identical comment lines in the file

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Duplicate comment removed
    Tool: Bash
    Preconditions: hooks/post-write.py has duplicate comment at lines 29-30
    Steps:
      1. Run `python3 -m py_compile hooks/post-write.py`
      2. Run `awk 'NR>1 && $0==prev {print NR": "$0} {prev=$0}' hooks/post-write.py`
    Expected Result: py_compile exits 0, awk produces no output (no consecutive duplicate lines)
    Failure Indicators: py_compile fails or awk shows duplicate lines
    Evidence: .sisyphus/evidence/task-2-no-duplicate-comment.txt
  ```

  **Commit**: YES — group with Wave 1
  - Message: `fix(hooks): remove duplicate comment in post-write.py`
  - Files: `hooks/post-write.py`
  - Pre-commit: `python3 -m py_compile hooks/post-write.py`

- [x] 3. Fix deprecated `datetime.utcnow()` in `hooks/prompt-enhancer.py` (F11)

  **What to do**:
  - At `hooks/prompt-enhancer.py:180`, replace `_dt.utcnow()` with `_dt.now(_dt.timezone.utc)` (or `datetime.now(timezone.utc)` depending on import style)
  - Check the file's existing import style for `datetime` — use the same pattern
  - Verify no other occurrences of `utcnow()` exist in the file

  **Must NOT do**:
  - DO NOT change any other logic in prompt-enhancer.py
  - DO NOT add new imports if `timezone` is already available

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-line replacement, well-defined fix
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2)
  - **Blocks**: T11
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `hooks/prompt-enhancer.py:1-20` — Import section, check how datetime is imported
  - `hooks/prompt-enhancer.py:180` — The deprecated `utcnow()` call
  - `hooks/session-start.py` or `hooks/circuit-breaker.py` — Check how other hooks handle datetime for consistency

  **WHY Each Reference Matters**:
  - Import section determines whether to use `datetime.now(timezone.utc)` or `_dt.now(_dt.timezone.utc)`
  - Other hooks show the project's established pattern for timezone-aware datetime

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/prompt-enhancer.py` → exit 0
  - [x] `grep -n 'utcnow' hooks/prompt-enhancer.py` → 0 matches

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: utcnow replaced with timezone-aware alternative
    Tool: Bash
    Preconditions: hooks/prompt-enhancer.py contains utcnow() at line ~180
    Steps:
      1. Run `python3 -m py_compile hooks/prompt-enhancer.py`
      2. Run `grep -c 'utcnow' hooks/prompt-enhancer.py`
      3. Run `grep -n 'timezone.utc\|tz=.*utc' hooks/prompt-enhancer.py`
    Expected Result: py_compile exits 0, grep -c returns 0, grep -n shows the new timezone-aware call
    Failure Indicators: utcnow still present, or py_compile fails
    Evidence: .sisyphus/evidence/task-3-no-utcnow.txt
  ```

  **Commit**: YES — group with Wave 1
  - Message: `fix(hooks): replace deprecated utcnow() with timezone-aware datetime`
  - Files: `hooks/prompt-enhancer.py`
  - Pre-commit: `python3 -m py_compile hooks/prompt-enhancer.py`

---

- [x] 4. Implement signal file mechanism for secret detection in `hooks/post-write.py` (F1 — P0)

  **What to do**:
  - At `hooks/post-write.py:156-158`, replace the `sys.exit(0)` after secret detection with:
    1. Write a JSON signal file to `.omg/state/secret-detected.json` containing: `{"timestamp": "...", "file": "<path>", "patterns_matched": ["..."], "action": "blocked"}`
    2. Print a CLEAR stderr warning: `"⚠ SECRET DETECTED in <file>. Signal written to .omg/state/secret-detected.json"`
    3. Keep `sys.exit(0)` — crash isolation preserved
  - Use `_resolve_project_dir()` from `_common.py` (added in T1) to locate `.omg/state/`
  - Ensure `.omg/state/` directory exists before writing (use `os.makedirs(..., exist_ok=True)`)
  - Import `_resolve_project_dir` from `_common`

  **Must NOT do**:
  - DO NOT change exit code from 0 — crash isolation policy
  - DO NOT modify the secret detection regex patterns
  - DO NOT add non-stdlib dependencies

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Security-critical change requiring careful understanding of the signal file contract and crash isolation
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `security-review`: Not needed — this is implementing a fix, not auditing for vulnerabilities

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T5, T6)
  - **Blocks**: T7
  - **Blocked By**: T1 (needs _resolve_project_dir), T2 (same file — post-write.py)

  **References**:

  **Pattern References**:
  - `hooks/post-write.py:140-176` — The secret detection section. Lines 156-158 are the exit-0 area
  - `hooks/post-write.py:1-30` — Import section and file header (import _resolve_project_dir here)
  - `hooks/_common.py:_resolve_project_dir()` — The helper added in T1, import and use it

  **API/Type References**:
  - Signal file schema: `{"timestamp": str (ISO 8601), "file": str, "patterns_matched": list[str], "action": "blocked"}`

  **External References**:
  - OMG README section "Standalone Architecture" — Documents crash isolation policy: "all OMG hooks exit 0 on internal errors"

  **WHY Each Reference Matters**:
  - Lines 140-176 show the complete secret detection flow — understand what triggers detection before modifying the outcome
  - README crash isolation policy confirms exit(0) must be preserved
  - _resolve_project_dir() is the safe way to find .omg/state/ directory

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/post-write.py` → exit 0
  - [x] `grep 'secret-detected.json' hooks/post-write.py` → match found (signal file path)
  - [x] `grep '_resolve_project_dir' hooks/post-write.py` → match found (helper imported)
  - [x] `grep 'sys.exit(0)' hooks/post-write.py` → still present (crash isolation preserved)
  - [x] `grep 'sys.exit(1)' hooks/post-write.py` → 0 matches (no non-zero exits)

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Signal file mechanism code present
    Tool: Bash
    Preconditions: hooks/post-write.py modified with signal file mechanism
    Steps:
      1. Run `python3 -m py_compile hooks/post-write.py`
      2. Run `grep -n 'secret-detected.json' hooks/post-write.py`
      3. Run `grep -n '_resolve_project_dir' hooks/post-write.py`
      4. Run `grep -c 'sys.exit(1)' hooks/post-write.py`
    Expected Result: py_compile exit 0, signal file path found, helper imported, zero exit(1) calls
    Failure Indicators: py_compile fails, signal path missing, exit(1) present
    Evidence: .sisyphus/evidence/task-4-signal-file-mechanism.txt

  Scenario: Crash isolation preserved
    Tool: Bash
    Preconditions: hooks/post-write.py modified
    Steps:
      1. Run `grep -c 'sys.exit(1)' hooks/post-write.py`
      2. Run `grep -c 'sys.exit(0)' hooks/post-write.py`
      3. Run `ast-grep --pattern 'sys.exit($N)' --lang python hooks/post-write.py` — verify all exit calls use 0
    Expected Result: exit(1) count = 0, exit(0) count ≥ 1
    Failure Indicators: Any non-zero exit code found
    Evidence: .sisyphus/evidence/task-4-crash-isolation.txt
  ```

  **Commit**: YES — group with Wave 2
  - Message: `security(hooks): implement secret detection signal file in post-write.py`
  - Files: `hooks/post-write.py`
  - Pre-commit: `python3 -m py_compile hooks/post-write.py`

- [x] 5. Fix NON_SOURCE_PATTERNS false positives in `hooks/stop_dispatcher.py` (F2 — P0)

  **What to do**:
  - At `hooks/stop_dispatcher.py:28-68`, modify the `NON_SOURCE_PATTERNS` list to fix false positives:
    1. Remove `"hooks/"` from the list — production hook code is source code
    2. Remove `"scripts/"` from the list — production scripts are source code
    3. Change `"test"` to more specific patterns: `".test."`, `"__test"`, `"_test."`, `"/tests/"`, `"/test/"` — prevents matching words like "contest", "protest"
    4. Change `"config"` to `"/config/"` or `".config."` — prevents matching `src/configure.py`
  - Also apply `_resolve_project_dir()` if os.getcwd() pattern exists in this file
  - Import `_resolve_project_dir` from `_common` if needed

  **Must NOT do**:
  - DO NOT change the matching engine/algorithm — only fix the pattern list
  - DO NOT refactor the stop_dispatcher architecture
  - DO NOT modify any other functions in the file

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Security-critical classification fix — incorrect patterns let modified production code skip verification
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T6)
  - **Blocks**: T8
  - **Blocked By**: T1 (needs _resolve_project_dir)

  **References**:

  **Pattern References**:
  - `hooks/stop_dispatcher.py:28-68` — The NON_SOURCE_PATTERNS list. Each pattern is a substring match.
  - `hooks/stop_dispatcher.py:170-185` — The `_is_non_source_path()` function that uses these patterns

  **WHY Each Reference Matters**:
  - Lines 28-68 is the exact list to modify — read every entry to understand what's there
  - Lines 170-185 shows HOW patterns are matched (substring `in` check) — determines what pattern format works

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/stop_dispatcher.py` → exit 0
  - [x] `grep '"hooks/"' hooks/stop_dispatcher.py` in NON_SOURCE_PATTERNS → 0 matches (removed)
  - [x] `grep '"scripts/"' hooks/stop_dispatcher.py` in NON_SOURCE_PATTERNS → 0 matches (removed)

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Production paths no longer classified as non-source
    Tool: Bash
    Preconditions: hooks/stop_dispatcher.py patterns modified
    Steps:
      1. Run `python3 -m py_compile hooks/stop_dispatcher.py`
      2. Run `grep -n '"hooks/"' hooks/stop_dispatcher.py` — should NOT appear in pattern list
      3. Run `grep -n '"scripts/"' hooks/stop_dispatcher.py` — should NOT appear in pattern list
      4. Run `grep -n '"test"' hooks/stop_dispatcher.py` — raw "test" should NOT appear (replaced with specific patterns)
    Expected Result: py_compile exit 0, no raw "hooks/", "scripts/", or "test" in pattern list
    Failure Indicators: Any of these broad patterns still present
    Evidence: .sisyphus/evidence/task-5-patterns-fixed.txt

  Scenario: Specific test patterns still work
    Tool: Bash
    Preconditions: hooks/stop_dispatcher.py patterns modified
    Steps:
      1. Run `grep -n '\.test\.' hooks/stop_dispatcher.py` — should find specific test pattern
      2. Run `grep -n '__test' hooks/stop_dispatcher.py` — should find specific test pattern
      3. Run `grep -n '/tests/' hooks/stop_dispatcher.py` — should find directory pattern
    Expected Result: All three specific patterns found in the file
    Failure Indicators: Specific patterns missing — tests would no longer be classified correctly
    Evidence: .sisyphus/evidence/task-5-test-patterns-present.txt
  ```

  **Commit**: YES — group with Wave 2
  - Message: `security(hooks): fix NON_SOURCE_PATTERNS false positives in stop_dispatcher.py`
  - Files: `hooks/stop_dispatcher.py`
  - Pre-commit: `python3 -m py_compile hooks/stop_dispatcher.py`

- [x] 6. Add audit logging before silent file deletions in `hooks/pre-compact.py` and `hooks/shadow_manager.py` (F4 — P1)

  **What to do**:
  - At `hooks/pre-compact.py:133` — before `shutil.rmtree(..., ignore_errors=True)`:
    1. Add `print(f"[OMG] Deleting: {path}", file=sys.stderr)` immediately before the rmtree call
    2. Optionally remove `ignore_errors=True` and replace with a try/except that logs the error
  - At `hooks/shadow_manager.py:236` — same pattern:
    1. Add `print(f"[OMG] Deleting: {path}", file=sys.stderr)` before rmtree
    2. Optionally replace `ignore_errors=True` with logged try/except
  - Use `_resolve_project_dir()` if os.getcwd() fallback exists in these files

  **Must NOT do**:
  - DO NOT use `logging.getLogger` — hooks use stderr
  - DO NOT add any new dependencies
  - DO NOT change the deletion logic itself (what gets deleted and when)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Two files with similar changes, needs careful placement of audit lines
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T4, T5)
  - **Blocks**: None
  - **Blocked By**: T1 (needs _resolve_project_dir if applicable)

  **References**:

  **Pattern References**:
  - `hooks/pre-compact.py:125-138` — The cleanup section with rmtree at line 133
  - `hooks/shadow_manager.py:230-240` — The cleanup section with rmtree at line 236
  - `hooks/tool-ledger.py` — Example of stderr logging pattern in hooks (follow same style)

  **WHY Each Reference Matters**:
  - Lines around rmtree show what variable holds the path being deleted
  - tool-ledger.py shows the established `print(f"[OMG] ...", file=sys.stderr)` pattern

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/pre-compact.py` → exit 0
  - [x] `python3 -m py_compile hooks/shadow_manager.py` → exit 0
  - [x] `grep -B2 'shutil.rmtree' hooks/pre-compact.py` → shows print/logging line within 2 lines before rmtree
  - [x] `grep -B2 'shutil.rmtree' hooks/shadow_manager.py` → shows print/logging line within 2 lines before rmtree

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Audit logging present before deletion in pre-compact.py
    Tool: Bash
    Preconditions: hooks/pre-compact.py modified with audit logging
    Steps:
      1. Run `python3 -m py_compile hooks/pre-compact.py`
      2. Run `grep -B2 'shutil.rmtree' hooks/pre-compact.py`
      3. Verify output contains print statement with stderr within 2 lines before rmtree
    Expected Result: py_compile exit 0, print(f"[OMG] Deleting: ...", file=sys.stderr) visible before rmtree
    Failure Indicators: No logging before rmtree call
    Evidence: .sisyphus/evidence/task-6-audit-precompact.txt

  Scenario: Audit logging present before deletion in shadow_manager.py
    Tool: Bash
    Preconditions: hooks/shadow_manager.py modified with audit logging
    Steps:
      1. Run `python3 -m py_compile hooks/shadow_manager.py`
      2. Run `grep -B2 'shutil.rmtree' hooks/shadow_manager.py`
      3. Verify output contains print statement with stderr within 2 lines before rmtree
    Expected Result: py_compile exit 0, print(f"[OMG] Deleting: ...", file=sys.stderr) visible before rmtree
    Failure Indicators: No logging before rmtree call
    Evidence: .sisyphus/evidence/task-6-audit-shadow.txt
  ```

  **Commit**: YES — group with Wave 2
  - Message: `security(hooks): add audit logging before silent file deletions`
  - Files: `hooks/pre-compact.py`, `hooks/shadow_manager.py`
  - Pre-commit: `python3 -m py_compile hooks/pre-compact.py && python3 -m py_compile hooks/shadow_manager.py`

- [x] 7. Harden exception handlers in `hooks/post-write.py` (F3 — P0, security-critical)

  **What to do**:
  - Find all `except Exception: pass` (and `except Exception as e: pass` equivalent silent handlers) in `hooks/post-write.py`
  - For each silent handler in a security-relevant path:
    1. Replace `pass` with `print(f"[OMG] post-write.py: {type(e).__name__}: {e}", file=sys.stderr)`
    2. If the except clause doesn't capture the exception, change `except Exception:` to `except Exception as e:`
  - For cleanup/non-critical handlers (e.g., temp file deletion): use `contextlib.suppress(OSError)` instead of bare `except Exception: pass`
  - Count handlers before and after — document the delta

  **Must NOT do**:
  - DO NOT change exit codes
  - DO NOT modify the secret detection logic (already handled in T4)
  - DO NOT touch cleanup handlers that are genuinely best as silent (file cleanup, temp removal)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multiple handler modifications in one file, needs judgment on which are security-relevant vs cleanup
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T8, T9, T10)
  - **Blocks**: None
  - **Blocked By**: T4 (post-write.py signal file must be in place first)

  **References**:
  **Pattern References**:
  - `hooks/post-write.py` (entire file) — Scan for all `except Exception` blocks
  - `hooks/tool-ledger.py` — Example of stderr error logging pattern

  **WHY Each Reference Matters**:
  - Need to identify ALL silent handlers in the file before deciding which to fix
  - tool-ledger.py shows the established error logging format

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/post-write.py` → exit 0
  - [x] `ast-grep --pattern 'except Exception: pass' --lang python hooks/post-write.py` → 0 matches

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: No silent exception handlers in security paths
    Tool: Bash
    Preconditions: hooks/post-write.py exception handlers modified
    Steps:
      1. Run `python3 -m py_compile hooks/post-write.py`
      2. Run `ast-grep --pattern 'except Exception: pass' --lang python hooks/post-write.py`
      3. Run `grep -c 'file=sys.stderr' hooks/post-write.py` — count stderr logging calls
    Expected Result: py_compile exit 0, ast-grep returns 0 matches, stderr logging count increased
    Failure Indicators: Silent handlers still present
    Evidence: .sisyphus/evidence/task-7-postwrite-exceptions.txt
  ```

  **Commit**: YES — group with Wave 3
  - Message: `security(hooks): harden exception handlers in post-write.py`
  - Files: `hooks/post-write.py`
  - Pre-commit: `python3 -m py_compile hooks/post-write.py`

- [x] 8. Harden exception handlers in `hooks/stop_dispatcher.py` (F3 — P0, security-critical)

  **What to do**:
  - `stop_dispatcher.py` has the HIGHEST density of silent handlers (~9). For each:
    1. Identify if the handler is in a security-relevant code path (verification, policy enforcement)
    2. Security paths: replace `pass` with `print(f"[OMG] stop_dispatcher: {type(e).__name__}: {e}", file=sys.stderr)`
    3. Cleanup paths: use `contextlib.suppress(OSError)` for file cleanup, or keep `pass` with a `# intentional: cleanup` comment
  - Add `import contextlib` at the top if not already present
  - Document each handler's disposition in a comment

  **Must NOT do**:
  - DO NOT change the NON_SOURCE_PATTERNS (already handled in T5)
  - DO NOT refactor the dispatcher architecture
  - DO NOT change any exit codes

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: ~9 handlers to evaluate individually, each needs security vs cleanup classification
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T7, T9, T10)
  - **Blocks**: None
  - **Blocked By**: T5 (stop_dispatcher.py patterns must be in place first)

  **References**:
  **Pattern References**:
  - `hooks/stop_dispatcher.py` (entire file) — Scan for all `except Exception` blocks (~9)
  - `hooks/stop_dispatcher.py:170-185` — `_is_non_source_path()` — this is security-critical, handler here MUST log

  **WHY Each Reference Matters**:
  - Full file scan needed to find all 9 handlers
  - Functions that determine verification enforcement are security-critical — their handlers must log

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/stop_dispatcher.py` → exit 0
  - [x] `ast-grep --pattern 'except Exception: pass' --lang python hooks/stop_dispatcher.py` → 0 matches

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: No silent exception handlers in security paths
    Tool: Bash
    Preconditions: hooks/stop_dispatcher.py exception handlers modified
    Steps:
      1. Run `python3 -m py_compile hooks/stop_dispatcher.py`
      2. Run `ast-grep --pattern 'except Exception: pass' --lang python hooks/stop_dispatcher.py`
      3. Run `grep -c 'file=sys.stderr' hooks/stop_dispatcher.py` — count stderr logging
    Expected Result: py_compile exit 0, ast-grep 0 matches, stderr count increased from baseline
    Failure Indicators: Silent handlers remain
    Evidence: .sisyphus/evidence/task-8-stopdispatcher-exceptions.txt
  ```

  **Commit**: YES — group with Wave 3
  - Message: `security(hooks): harden exception handlers in stop_dispatcher.py`
  - Files: `hooks/stop_dispatcher.py`
  - Pre-commit: `python3 -m py_compile hooks/stop_dispatcher.py`

- [x] 9. Harden exception handlers in `hooks/config-guard.py` (F3 — P0, security-critical)

  **What to do**:
  - Find all `except Exception: pass` handlers in `hooks/config-guard.py` (~5 expected)
  - For each: same classification as T7/T8:
    1. Security paths (settings mutation detection): log to stderr
    2. Cleanup paths: use `contextlib.suppress(OSError)` or annotate with `# intentional: cleanup`
  - Add `import contextlib` if needed

  **Must NOT do**:
  - DO NOT change the config mutation detection logic
  - DO NOT change exit codes

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: ~5 handlers to evaluate, same pattern as T7/T8
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T7, T8, T10)
  - **Blocks**: None
  - **Blocked By**: None (config-guard.py not touched by prior waves)

  **References**:
  **Pattern References**:
  - `hooks/config-guard.py` (entire file, 161 LOC) — Scan for all `except Exception` blocks

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/config-guard.py` → exit 0
  - [x] `ast-grep --pattern 'except Exception: pass' --lang python hooks/config-guard.py` → 0 matches

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: No silent exception handlers in config-guard
    Tool: Bash
    Preconditions: hooks/config-guard.py exception handlers modified
    Steps:
      1. Run `python3 -m py_compile hooks/config-guard.py`
      2. Run `ast-grep --pattern 'except Exception: pass' --lang python hooks/config-guard.py`
    Expected Result: py_compile exit 0, 0 matches from ast-grep
    Failure Indicators: Silent handlers remain
    Evidence: .sisyphus/evidence/task-9-configguard-exceptions.txt
  ```

  **Commit**: YES — group with Wave 3
  - Message: `security(hooks): harden exception handlers in config-guard.py`
  - Files: `hooks/config-guard.py`
  - Pre-commit: `python3 -m py_compile hooks/config-guard.py`

- [x] 10. Harden critical-write exception handlers in `hooks/_common.py` (F3 — P0, limited scope)

  **What to do**:
  - Find `except Exception: pass` handlers in `hooks/_common.py` that guard WRITE operations (json.dump, file write)
  - For write-path handlers: log to stderr before passing
  - For read-path handlers: keep silent (non-critical)
  - **CRITICAL**: DO NOT modify `setup_crash_handler()` — it's the outer safety net for all hooks

  **Must NOT do**:
  - **DO NOT modify `setup_crash_handler()`** — this is the #1 guardrail
  - DO NOT change any function signatures
  - DO NOT add non-stdlib imports

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Must carefully distinguish write-path vs read-path handlers, highest blast radius file
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T7, T8, T9)
  - **Blocks**: None
  - **Blocked By**: T1 (_common.py must have _resolve_project_dir added first)

  **References**:
  **Pattern References**:
  - `hooks/_common.py` (entire file, 269 LOC) — Scan for all `except Exception` blocks
  - `hooks/_common.py:setup_crash_handler()` — **READ ONLY, DO NOT MODIFY** — understand what it does so you don't accidentally change it

  **WHY Each Reference Matters**:
  - setup_crash_handler() is imported by ALL 19 hooks — any change breaks everything
  - Write-path handlers (json.dump, open().write) are where silent failure causes data loss

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/_common.py` → exit 0
  - [x] `grep -A3 'def setup_crash_handler' hooks/_common.py` → unchanged from before T10
  - [x] Silent handlers in write paths replaced with stderr logging

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: setup_crash_handler untouched
    Tool: Bash
    Preconditions: hooks/_common.py modified for exception handlers
    Steps:
      1. Run `python3 -m py_compile hooks/_common.py`
      2. Run `git diff hooks/_common.py | grep -A5 'setup_crash_handler'`
      3. Verify no changes inside setup_crash_handler function body
    Expected Result: py_compile exit 0, git diff shows NO changes inside setup_crash_handler
    Failure Indicators: Any modification to setup_crash_handler function
    Evidence: .sisyphus/evidence/task-10-common-crash-handler-safe.txt

  Scenario: Write-path handlers now log
    Tool: Bash
    Preconditions: hooks/_common.py modified
    Steps:
      1. Run `grep -B2 -A2 'json.dump\|open.*write\|\.write(' hooks/_common.py`
      2. Verify nearby exception handlers include stderr logging
    Expected Result: Write operations have visible error handling nearby
    Failure Indicators: Write operations still wrapped in silent except blocks
    Evidence: .sisyphus/evidence/task-10-common-write-handlers.txt
  ```

  **Commit**: YES — group with Wave 3
  - Message: `security(hooks): harden critical-write exception handlers in _common.py`
  - Files: `hooks/_common.py`
  - Pre-commit: `python3 -m py_compile hooks/_common.py`

- [x] 11. Fix word-boundary matching and knowledge index validation in `hooks/prompt-enhancer.py` (F8 + F10 — P2)

  **What to do**:
  - **F8 (Word-boundary matching)**:
    1. Find the intent classification signal lists (English keywords like `"fix"`, `"test"`, `"auth"`)
    2. For Latin/English tokens: wrap matches in word-boundary checks — use `re.search(r'\b' + re.escape(keyword) + r'\b', text)` instead of `keyword in text`
    3. For Korean/Hangul tokens (e.g., `"인증"`, `"보안"`, `"디자인"`): KEEP substring matching — Korean has no word boundaries
    4. Split the matching logic: regex for Latin, substring for Korean
  - **F10 (Knowledge index validation)**:
    1. At `hooks/prompt-enhancer.py:440-453`, add `isinstance(index, dict)` check after loading `.index.json`
    2. If not a dict: delete and rebuild (existing behavior) but add stderr warning
    3. Consolidate the 4 separate except blocks into a cleaner structure with logging

  **Must NOT do**:
  - DO NOT add word-boundary regex to Korean tokens
  - DO NOT add schema validation libraries (no pydantic, no jsonschema)
  - DO NOT change the knowledge retrieval algorithm

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Two interleaved fixes in the same file, Korean/Latin matching split requires careful implementation
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `frontend-patterns`: Not relevant — this is a Python hook, not frontend code

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T12, T13, T14)
  - **Blocks**: None
  - **Blocked By**: T3 (utcnow fix in same file must be done first)

  **References**:
  **Pattern References**:
  - `hooks/prompt-enhancer.py:100-200` — Intent classification signal lists and matching logic
  - `hooks/prompt-enhancer.py:440-453` — Knowledge index loading with 4 except blocks
  - `hooks/prompt-enhancer.py` — Search for Korean characters (가-힣) to identify Hangul signal tokens

  **WHY Each Reference Matters**:
  - Signal lists show exactly which keywords need word-boundary vs substring matching
  - The 4 except blocks at 440-453 need consolidation, so read all of them to understand failure modes
  - Korean detection: if a token contains Hangul characters, keep it as substring match

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile hooks/prompt-enhancer.py` → exit 0
  - [x] `grep -c 're.search.*\\b' hooks/prompt-enhancer.py` → >0 (word-boundary regex used for Latin tokens)
  - [x] `grep -c 'isinstance.*dict' hooks/prompt-enhancer.py` → >0 (index type check added)

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Word-boundary matching for Latin tokens
    Tool: Bash
    Preconditions: hooks/prompt-enhancer.py modified with word-boundary matching
    Steps:
      1. Run `python3 -m py_compile hooks/prompt-enhancer.py`
      2. Run `grep -n 're.search.*\\b' hooks/prompt-enhancer.py` — verify regex word boundaries used
      3. Run `grep -n '"fix"\|"test"' hooks/prompt-enhancer.py` — check these aren't used with `in` anymore
    Expected Result: py_compile exit 0, word-boundary patterns present, raw substring `in` removed for English tokens
    Failure Indicators: English tokens still matched with `in` operator
    Evidence: .sisyphus/evidence/task-11-word-boundary.txt

  Scenario: Korean tokens preserved as substring
    Tool: Bash
    Preconditions: hooks/prompt-enhancer.py modified
    Steps:
      1. Run `grep -P '[\x{AC00}-\x{D7A3}]' hooks/prompt-enhancer.py` or `grep '인증\|보안' hooks/prompt-enhancer.py`
      2. Verify Korean tokens are NOT wrapped in word-boundary regex
    Expected Result: Korean tokens present and used with substring matching (not regex)
    Failure Indicators: Korean tokens wrapped in \b patterns
    Evidence: .sisyphus/evidence/task-11-korean-preserved.txt

  Scenario: Knowledge index validation added
    Tool: Bash
    Preconditions: hooks/prompt-enhancer.py knowledge index section modified
    Steps:
      1. Run `grep -n 'isinstance.*dict' hooks/prompt-enhancer.py`
      2. Run `grep -A2 'isinstance.*dict' hooks/prompt-enhancer.py` — verify it's near index loading
    Expected Result: isinstance check found near .index.json loading code
    Failure Indicators: No type check on loaded index
    Evidence: .sisyphus/evidence/task-11-index-validation.txt
  ```

  **Commit**: YES — group with Wave 4
  - Message: `fix(hooks): add word-boundary matching for Latin tokens and validate knowledge index`
  - Files: `hooks/prompt-enhancer.py`
  - Pre-commit: `python3 -m py_compile hooks/prompt-enhancer.py`

- [x] 12. Add stderr warning for `--host 0.0.0.0` in `control_plane/server.py` (F5 — P2)

  **What to do**:
  - After argument parsing in `control_plane/server.py`, add a check:
    ```python
    if args.host != "127.0.0.1":
        print(f"\u26a0 WARNING: Binding to {args.host} exposes the control plane to the network. No authentication is configured.", file=sys.stderr)
    ```
  - Place the warning after `args = parser.parse_args()` and before `run_server()`

  **Must NOT do**:
  - DO NOT add authentication middleware
  - DO NOT change the default host from 127.0.0.1
  - DO NOT block the --host flag

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 3-line addition to one file
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T11, T13, T14)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `control_plane/server.py:81-104` — Server startup, argparse, run_server call

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile control_plane/server.py` → exit 0
  - [x] `grep 'WARNING.*host.*network' control_plane/server.py` → match found

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Warning present for non-localhost binding
    Tool: Bash
    Preconditions: control_plane/server.py modified
    Steps:
      1. Run `python3 -m py_compile control_plane/server.py`
      2. Run `grep -n 'WARNING.*host\|WARNING.*network\|WARNING.*authentication' control_plane/server.py`
    Expected Result: py_compile exit 0, warning message found
    Failure Indicators: No warning for non-localhost binding
    Evidence: .sisyphus/evidence/task-12-host-warning.txt
  ```

  **Commit**: YES — group with Wave 4
  - Message: `fix(control-plane): warn when binding to non-localhost address`
  - Files: `control_plane/server.py`
  - Pre-commit: `python3 -m py_compile control_plane/server.py`

- [x] 13. Cache `shutil.which` result in `runtime/team_router.py` (F6 — P2)

  **What to do**:
  - At `runtime/team_router.py:126`, `_check_tool_available(tool_bin)` is called for the dispatch decision
  - At `runtime/team_router.py:160`, the SAME function is called again for the evidence dict
  - Fix: store the result of the first call in a local variable, reuse it at line 160
    ```python
    tool_available = _check_tool_available(tool_bin)  # line ~126
    # ... use tool_available ...
    # line ~160: reuse tool_available instead of calling _check_tool_available again
    ```

  **Must NOT do**:
  - DO NOT change the _check_tool_available function itself
  - DO NOT add module-level caching (overkill for this fix)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Variable extraction, 2-line change
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T11, T12, T14)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `runtime/team_router.py:84-100` — `_check_tool_available` function definition
  - `runtime/team_router.py:120-170` — The dispatch function with both call sites

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile runtime/team_router.py` → exit 0
  - [x] `grep -c '_check_tool_available' runtime/team_router.py` → count reduced by 1 (one call site replaced with variable)

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Redundant call eliminated
    Tool: Bash
    Preconditions: runtime/team_router.py modified
    Steps:
      1. Run `python3 -m py_compile runtime/team_router.py`
      2. Run `grep -n '_check_tool_available' runtime/team_router.py`
      3. Count call sites (not definition) — should be 1, not 2
    Expected Result: py_compile exit 0, only 1 call site (+ 1 definition)
    Failure Indicators: Still 2 call sites
    Evidence: .sisyphus/evidence/task-13-cached-which.txt
  ```

  **Commit**: YES — group with Wave 4
  - Message: `fix(runtime): cache shutil.which result in team_router.py`
  - Files: `runtime/team_router.py`
  - Pre-commit: `python3 -m py_compile runtime/team_router.py`

- [x] 14. Add path-prefix assertions for `rm -rf` in `OMG-setup.sh` (F9 — P2)

  **What to do**:
  - At `OMG-setup.sh` lines 518, 935, 939, `rm -rf` operates on constructed paths
  - Before each `rm -rf`, add a path-prefix assertion:
    ```bash
    # Verify the target path is under expected directory before deletion
    [[ "$TARGET_PATH" == "$CLAUDE_DIR"* ]] || { echo "ERROR: rm -rf target outside expected directory: $TARGET_PATH" >&2; exit 1; }
    ```
  - This ensures `rm -rf` never operates on a path outside the expected `$CLAUDE_DIR` scope

  **Must NOT do**:
  - DO NOT add interactive confirmation prompts
  - DO NOT change the deletion logic
  - DO NOT modify `$DRY_RUN` behavior

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 3 assertion lines added to a shell script
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T11, T12, T13)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `OMG-setup.sh:515-520` — First rm -rf area
  - `OMG-setup.sh:930-940` — Second and third rm -rf areas
  - `OMG-setup.sh:1-30` — Variable definitions ($CLAUDE_DIR, $DRY_RUN)

  **WHY Each Reference Matters**:
  - Need to know the variable names used in each rm -rf to write correct assertions
  - $CLAUDE_DIR is the expected parent directory for all deletions

  **Acceptance Criteria**:
  - [x] `bash -n OMG-setup.sh` → exit 0 (syntax valid)
  - [x] Each `rm -rf` has a preceding path assertion within 3 lines

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Path assertions present before rm -rf
    Tool: Bash
    Preconditions: OMG-setup.sh modified with path assertions
    Steps:
      1. Run `bash -n OMG-setup.sh`
      2. Run `grep -B3 'rm -rf' OMG-setup.sh`
      3. Verify each rm -rf has a preceding assertion line
    Expected Result: bash -n exit 0, every rm -rf preceded by path assertion
    Failure Indicators: rm -rf without preceding path check
    Evidence: .sisyphus/evidence/task-14-path-assertions.txt
  ```

  **Commit**: YES — group with Wave 4
  - Message: `fix(installer): add path-prefix assertions before rm -rf operations`
  - Files: `OMG-setup.sh`
  - Pre-commit: `bash -n OMG-setup.sh`

- [x] 15. Apply `_resolve_project_dir()` across remaining hooks (F7 Sweep)

  **What to do**:
  - Find ALL remaining hooks that use `os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())`
  - Replace each occurrence with `_resolve_project_dir()` from `_common`
  - Add `from hooks._common import _resolve_project_dir` (or adjust import style to match file) if not already imported
  - Files likely affected (not already touched by prior tasks):
    - `hooks/circuit-breaker.py`
    - `hooks/session-start.py`
    - `hooks/tool-ledger.py`
    - `hooks/test-validator.py`
    - `hooks/trust_review.py`
    - Others — scan with grep to find all

  **Must NOT do**:
  - DO NOT modify files already changed in prior waves (post-write.py, stop_dispatcher.py, config-guard.py, _common.py, pre-compact.py, shadow_manager.py, prompt-enhancer.py)
  - DO NOT change any logic beyond the project dir resolution

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multiple files with mechanical changes, but needs grep-first to identify all targets
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5 (standalone)
  - **Blocks**: None
  - **Blocked By**: T1 (helper must exist), T4-T11 (files from prior waves must be stable)

  **References**:
  **Pattern References**:
  - `grep -r 'os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())' hooks/` — Run this first to find all files needing changes
  - `hooks/_common.py:_resolve_project_dir()` — The helper function to import and use

  **WHY Each Reference Matters**:
  - grep output is the task's input — tells you exactly which files need the one-line change
  - _common.py helper is what you're replacing the pattern with

  **Acceptance Criteria**:
  - [x] `python3 -m py_compile <each modified file>` → exit 0 for all
  - [x] `grep -r 'os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())' hooks/` → 0 matches

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: No remaining raw os.getcwd() fallback in hooks
    Tool: Bash
    Preconditions: All remaining hooks updated with _resolve_project_dir()
    Steps:
      1. Run `grep -r 'os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())' hooks/`
      2. Run `for f in hooks/*.py; do python3 -m py_compile "$f" && echo "OK: $f" || echo "FAIL: $f"; done`
    Expected Result: grep returns 0 matches, all py_compile pass
    Failure Indicators: Any remaining raw os.getcwd() pattern, any compile failure
    Evidence: .sisyphus/evidence/task-15-sweep-complete.txt

  Scenario: _resolve_project_dir imported in affected files
    Tool: Bash
    Preconditions: Files modified in this task
    Steps:
      1. Run `grep -l '_resolve_project_dir' hooks/*.py` — list files that import the helper
      2. Compare against files that previously had os.getcwd() pattern
    Expected Result: All files that had the old pattern now import _resolve_project_dir
    Failure Indicators: File has neither old pattern nor new helper
    Evidence: .sisyphus/evidence/task-15-imports-verified.txt
  ```

  **Commit**: YES — Wave 5
  - Message: `refactor(hooks): apply _resolve_project_dir across all hooks`
  - Files: all modified hook files
  - Pre-commit: `for f in hooks/*.py; do python3 -m py_compile "$f" || exit 1; done`

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, grep for pattern). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m py_compile` on ALL modified .py files. Run `bash -n` on modified .sh files. Review all changed files for: `as any`/`@ts-ignore` equivalents, empty catches remaining in security files, `print()` without `file=sys.stderr` in hooks, unused imports. Check AI slop: excessive comments, over-abstraction, generic variable names.
  Output: `Compile [PASS/FAIL] | Lint [N clean/N issues] | VERDICT`

- [x] F3. **Real QA — Pattern Verification** — `unspecified-high`
  Run ALL verification commands from every task's QA scenarios. Capture output as evidence. Specifically verify:
  - `ast-grep --pattern 'except Exception: pass' --lang python hooks/post-write.py hooks/stop_dispatcher.py hooks/config-guard.py` → 0 matches
  - `grep -r 'os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())' hooks/` → 0 matches
  - `grep -r 'utcnow()' hooks/` → 0 matches
  - `grep -r 'ignore_errors=True' hooks/pre-compact.py hooks/shadow_manager.py` → 0 matches (or audit log within 2 lines before each)
  Save to `.sisyphus/evidence/final-qa/`.
  Output: `Patterns [N/N verified] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git diff). Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes. Verify no changes to `_common.py:setup_crash_handler()`.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `fix(hooks): add _resolve_project_dir helper and trivial fixes` — _common.py, post-write.py, prompt-enhancer.py
- **Wave 2**: `security(hooks): implement secret signal file, fix pattern classification, add deletion audit` — post-write.py, stop_dispatcher.py, pre-compact.py, shadow_manager.py
- **Wave 3**: `security(hooks): harden exception handlers in security-critical paths` — post-write.py, stop_dispatcher.py, config-guard.py, _common.py
- **Wave 4**: `fix(omg): P2 remediation — word-boundary, warnings, caching, assertions` — prompt-enhancer.py, server.py, team_router.py, OMG-setup.sh
- **Wave 5**: `refactor(hooks): apply _resolve_project_dir across remaining hooks` — remaining hook files

---

## Success Criteria

### Verification Commands
```bash
# All modified .py files compile
for f in hooks/post-write.py hooks/stop_dispatcher.py hooks/config-guard.py hooks/_common.py hooks/pre-compact.py hooks/shadow_manager.py hooks/prompt-enhancer.py control_plane/server.py runtime/team_router.py; do python3 -m py_compile "$f" && echo "OK: $f" || echo "FAIL: $f"; done

# No silent exception handlers in security-critical files
ast-grep --pattern 'except Exception: pass' --lang python hooks/post-write.py hooks/stop_dispatcher.py hooks/config-guard.py

# No raw os.getcwd() fallback in hooks
grep -r 'os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())' hooks/

# No deprecated utcnow
grep -r 'utcnow()' hooks/

# Shell script syntax valid
bash -n OMG-setup.sh
```

### Final Checklist
- [x] All "Must Have" items present and verified
- [x] All "Must NOT Have" guardrails respected
- [x] All evidence files present in `.sisyphus/evidence/`
- [x] All modified files compile/parse without errors
- [x] Zero silent exception handlers in security-critical paths
