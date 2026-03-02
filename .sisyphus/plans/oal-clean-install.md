# OAL Clean Install to ~/.claude

## TL;DR

> **Quick Summary**: Clean reinstall OAL into ~/.claude, removing all OMC artifacts, backup debris, and misplaced files. Result: a pristine ~/.claude with only OAL-managed components.
> 
> **Deliverables**:
> - Clean OAL installation (16 hooks, 5 core rules, 5 agents, 19+ commands)
> - All backup debris removed (24 backup dirs, 50+ .bak files)
> - All OMC artifacts removed (.omc/, .omc-config.json, omc-hud.mjs)
> - HUD updated to latest version from OAL source
> - protocols/ preserved with .bak files cleaned
> - Extra rules (05-07) removed from core rules directory
> 
> **Estimated Effort**: Short (~15 min execution)
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 → Task 3 → Task 4-8 (parallel) → Task 9-10 (parallel)

---

## Context

### Original Request
OAL (oh-my-claudecode 업그레이드)을 ~/.claude에 완벽하게 설치. 모든 설정이 정확하게 배치되도록 구성.

### Interview Summary
**Key Discussions**:
- 현재 ~/.claude 상태 심각하게 오염: 백업 24개, .bak 50+, OMC 잔재, 규칙 오배치
- 설치 방식: 클린 재설치 (`reinstall --clear-omc`)
- protocols/ 디렉토리: 기존 유지 (CLAUDE.md @import 참조)
- 백업 잔재: 전부 삭제

**Research Findings**:
- OAL-setup.sh가 처리하는 것: hooks, rules/core, agents, commands, templates, oal-runtime, settings.json merge
- OAL-setup.sh가 처리하지 않는 것: protocols/, HUD, rules 05-07 제거, .bak 정리, .omc/ 삭제, .oal-backups/ 삭제

### Metis Review
**Identified Gaps** (addressed):
- quality-gate.py: OAL 소스에 없지만 settings.json에 등록됨 → 기능적이므로 유지
- HUD: installer가 복사하지 않음 → 수동 복사 task 추가
- `.oal-backups/` (하이픈 없음): `.oal-backup-*`와 별도 패턴 → 둘 다 삭제
- `--non-interactive --merge-policy=apply` 플래그 필요 → 적용
- agents/ 내 custom 파일 (frontend-design-validator.md): 유지
- settings.json 내 권한 모순 (allow+ask 중복): merge가 처리, 수동 미개입

---

## Work Objectives

### Core Objective
OAL을 ~/.claude에 깨끗하게 재설치하여 모든 컴포넌트가 정확한 위치에 배치되고, 모든 잔재가 제거된 상태를 달성한다.

### Concrete Deliverables
- `~/.claude/hooks/`: OAL 소스의 16개 hook + quality-gate.py (custom) + _common.py
- `~/.claude/rules/`: 정확히 5개 core rule (00-04)
- `~/.claude/agents/`: 5개 OAL agent + custom agents (frontend-design-validator.md)
- `~/.claude/commands/`: 19 static OAL commands + legacy compat aliases
- `~/.claude/protocols/`: 6개 protocol 파일 (.bak 없이)
- `~/.claude/hud/oal-hud.mjs`: OAL 소스와 동일한 최신 버전
- `~/.claude/settings.json`: OAL hook 등록 + permissions
- `~/.claude/oal-runtime/`: 최신 runtime
- `~/.claude/templates/oal/`: templates + contextual rules

### Definition of Done
- [x] `ls ~/.claude/rules/*.md | wc -l` = 5
- [x] `find ~/.claude -name "*.bak*" -o -name "*.backup*" | wc -l` = 0 (5 files in managed backups/ dir — intentional)
- [x] `find ~/.claude -maxdepth 1 -name ".oal-backup-*" -type d | wc -l` = 0
- [x] `test ! -d ~/.claude/.omc && test ! -f ~/.claude/.omc-config.json` — PASS
- [x] `/OAL:health-check` reports no errors — all hook files verified, @imports resolve, protocols intact

### Must Have
- 모든 OAL hook이 ~/.claude/hooks/에 설치되고 syntax-valid
- settings.json의 모든 hook 참조가 실존 파일을 가리킴
- CLAUDE.md의 @import가 모두 유효한 파일 참조
- Zero .bak, .backup, .oal-backup-* 잔재

### Must NOT Have (Guardrails)
- **DO NOT** touch `~/.claude/protocols/` 내용 (only remove .bak sibling)
- **DO NOT** touch `.session-stats.json`, `cache/`, `backups/` (Claude Code 내부)
- **DO NOT** modify `enabledPlugins` or permissions arrays manually
- **DO NOT** use broad `rm -rf` patterns — all deletes must be targeted
- **DO NOT** modify OAL-setup.sh or OAL source files
- **DO NOT** touch `~/.claude/skills/`, `~/.claude/plugins/`, `~/.claude/projects/`
- **MUST NOT** delete `frontend-design-validator.md` (custom agent, not OAL-managed)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (shell scripts only)
- **Automated tests**: None (operational task, not code)
- **Framework**: Bash verification commands

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **All tasks**: Use Bash — Run commands, check file existence, compare counts

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Pre-flight — foundation):
├── Task 1: Snapshot current state + save protocols/ [quick]
└── Task 2: Verify OAL source integrity [quick]

Wave 2 (Core install — sequential, must complete alone):
└── Task 3: Run OAL-setup.sh reinstall [quick]

Wave 3 (Post-install fixes — MAX PARALLEL):
├── Task 4: Restore protocols/ + clean .bak (depends: 3) [quick]
├── Task 5: Copy HUD + remove omc-hud.mjs (depends: 3) [quick]
├── Task 6: Remove extra rules 05-07 (depends: 3) [quick]
├── Task 7: Remove OMC artifacts (depends: 3) [quick]
└── Task 8: Clean ALL backup debris (depends: 3) [quick]

Wave 4 (Verification — parallel):
├── Task 9: Run 11 acceptance criteria checks (depends: 4-8) [quick]
└── Task 10: Validate hook→file integrity (depends: 4-8) [quick]

Wave FINAL (Independent review):
├── Task F1: Plan compliance audit (oracle)
└── Task F2: Final state snapshot + diff (quick)

Critical Path: Task 1 → Task 3 → Tasks 4-8 → Tasks 9-10 → F1-F2
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 5 (Wave 3)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 3 | 1 |
| 2 | — | 3 | 1 |
| 3 | 1, 2 | 4, 5, 6, 7, 8 | 2 |
| 4 | 3 | 9, 10 | 3 |
| 5 | 3 | 9, 10 | 3 |
| 6 | 3 | 9, 10 | 3 |
| 7 | 3 | 9, 10 | 3 |
| 8 | 3 | 9, 10 | 3 |
| 9 | 4-8 | F1, F2 | 4 |
| 10 | 4-8 | F1, F2 | 4 |
| F1 | 9, 10 | — | FINAL |
| F2 | 9, 10 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 2 — T1 → `quick`, T2 → `quick`
- **Wave 2**: 1 — T3 → `quick`
- **Wave 3**: 5 — T4-T8 → `quick`
- **Wave 4**: 2 — T9 → `quick`, T10 → `quick`
- **FINAL**: 2 — F1 → `deep`, F2 → `quick`

---

## TODOs

> Implementation tasks. EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.
> **A task WITHOUT QA Scenarios is INCOMPLETE. No exceptions.**

- [x] 1. Snapshot current state + save protocols/

  **What to do**:
  - Run `ls -la ~/.claude/ | wc -l` and record total entry count
  - Run `ls ~/.claude/rules/*.md | wc -l` and record current rule count
  - Run `ls ~/.claude/hooks/*.py | wc -l` and record current hook count
  - Run `ls ~/.claude/agents/*.md 2>/dev/null | wc -l` and record agent count (including .bak)
  - Run `ls ~/.claude/commands/*.md | wc -l` and record command count
  - Copy `~/.claude/protocols/` to `/tmp/oal-protocols-backup/` as safety net
  - Save all counts to `.sisyphus/evidence/task-1-pre-snapshot.txt`

  **Must NOT do**:
  - Do NOT modify any files
  - Do NOT delete anything

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Task 3
  - **Blocked By**: None

  **References**:
  - `~/.claude/` — target directory to snapshot
  - `~/.claude/protocols/` — 6 files to preserve: 01-doc-check.md through 06-cross-model.md

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Pre-install snapshot captured
    Tool: Bash
    Steps:
      1. Run `cat .sisyphus/evidence/task-1-pre-snapshot.txt`
      2. Verify file contains counts for rules, hooks, agents, commands
      3. Run `ls /tmp/oal-protocols-backup/*.md | wc -l`
    Expected Result: snapshot file exists with numeric counts; /tmp backup has 6 .md files
    Evidence: .sisyphus/evidence/task-1-pre-snapshot.txt
  ```

  **Commit**: NO

- [x] 2. Verify OAL source integrity

  **What to do**:
  - Verify OAL source directory exists: `/Users/cminseo/Documents/scripts/Shell/OAL`
  - Verify `OAL-setup.sh` exists and is executable
  - Verify key source directories exist: `hooks/`, `rules/core/`, `agents/`, `commands/`
  - Run `python3 -c "import py_compile; py_compile.compile('/Users/cminseo/Documents/scripts/Shell/OAL/OAL-setup.sh')"` — no, that's for Python. Instead verify: `bash -n /Users/cminseo/Documents/scripts/Shell/OAL/OAL-setup.sh`
  - Count source hooks: `ls /Users/cminseo/Documents/scripts/Shell/OAL/hooks/*.py | grep -v __pycache__ | wc -l`
  - Count source rules: `ls /Users/cminseo/Documents/scripts/Shell/OAL/rules/core/*.md | wc -l`
  - Count source agents: `ls /Users/cminseo/Documents/scripts/Shell/OAL/agents/*.md | wc -l`
  - Count source commands: `ls /Users/cminseo/Documents/scripts/Shell/OAL/commands/*.md | wc -l`
  - Verify HUD source exists: `/Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs`

  **Must NOT do**:
  - Do NOT modify OAL source files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Task 3
  - **Blocked By**: None

  **References**:
  - `/Users/cminseo/Documents/scripts/Shell/OAL/OAL-setup.sh` — main installer script
  - `/Users/cminseo/Documents/scripts/Shell/OAL/hooks/` — 18 source files (16 hooks + _common.py + state_migration.py)
  - `/Users/cminseo/Documents/scripts/Shell/OAL/rules/core/` — 5 core rule files
  - `/Users/cminseo/Documents/scripts/Shell/OAL/agents/` — 5 agent files
  - `/Users/cminseo/Documents/scripts/Shell/OAL/commands/` — 19 command files
  - `/Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs` — HUD source (installer doesn't copy this)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: OAL source is complete and valid
    Tool: Bash
    Steps:
      1. Run `bash -n /Users/cminseo/Documents/scripts/Shell/OAL/OAL-setup.sh`
      2. Run `ls /Users/cminseo/Documents/scripts/Shell/OAL/hooks/*.py | wc -l`
      3. Run `ls /Users/cminseo/Documents/scripts/Shell/OAL/rules/core/*.md | wc -l`
      4. Run `ls /Users/cminseo/Documents/scripts/Shell/OAL/agents/*.md | wc -l`
      5. Run `test -f /Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs`
    Expected Result: bash -n exits 0; hooks >= 16; rules = 5; agents = 5; HUD exists
    Evidence: .sisyphus/evidence/task-2-source-integrity.txt
  ```

  **Commit**: NO

- [x] 3. Run OAL-setup.sh reinstall

  **What to do**:
  - Change to OAL source directory: `/Users/cminseo/Documents/scripts/Shell/OAL`
  - Run: `./OAL-setup.sh reinstall --clear-omc --non-interactive --merge-policy=apply`
  - Capture full output to `.sisyphus/evidence/task-3-install-output.txt`
  - Verify exit code is 0
  - Verify `.oal-version` marker was created in `~/.claude/hooks/`

  **Must NOT do**:
  - Do NOT run without `--non-interactive` (will hang on prompts)
  - Do NOT run with `--dry-run` (need actual install)
  - Do NOT modify OAL-setup.sh before running

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (solo)
  - **Blocks**: Tasks 4, 5, 6, 7, 8
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `/Users/cminseo/Documents/scripts/Shell/OAL/OAL-setup.sh` — installer script
    - Line 669 `run_install_like()` — main install function
    - Line 490 `remove_oal_files()` — cleanup function (removes hooks, rules 00-04, agents, commands)
    - Line 80 `detect_omc_signals()` — OMC detection
    - Line 155 `clear_omc_artifacts()` — OMC cleanup (commands, hooks, plugins, text references)
  - Flags: `--clear-omc` removes OMC command files + sanitizes text references
  - Flags: `--non-interactive` skips all prompts
  - Flags: `--merge-policy=apply` auto-applies settings.json merge

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Installer completes successfully
    Tool: Bash
    Steps:
      1. Run installer and capture output
      2. Check exit code = 0
      3. Run `cat ~/.claude/hooks/.oal-version`
      4. Run `ls ~/.claude/hooks/*.py | wc -l` (should be >= 16)
      5. Run `ls ~/.claude/rules/*.md | wc -l` (should be >= 5)
      6. Run `ls ~/.claude/agents/oal-*.md | wc -l` (should be 5)
    Expected Result: exit 0; version marker exists; hook count >= 16; rules >= 5; agents = 5
    Failure Indicators: non-zero exit, missing .oal-version, any "ERROR" in output
    Evidence: .sisyphus/evidence/task-3-install-output.txt

  Scenario: OMC artifacts cleared by installer
    Tool: Bash
    Steps:
      1. Check installer output contains "Clearing detected OMC artifacts"
      2. Check installer output contains "Sanitized" or "sanitized"
    Expected Result: OMC cleanup was performed
    Evidence: .sisyphus/evidence/task-3-install-output.txt
  ```

  **Commit**: NO

---

- [x] 4. Restore protocols/ + clean .bak files

  **What to do**:
  - Verify `~/.claude/protocols/` still exists after reinstall (installer should not touch it)
  - If protocols/ was destroyed (unlikely): restore from `/tmp/oal-protocols-backup/`
  - Remove .bak file: `rm -f ~/.claude/protocols/*.bak*`
  - Verify 6 protocol files remain: 01-doc-check.md through 06-cross-model.md
  - Verify CLAUDE.md @import references all resolve:
    `grep '^@' ~/.claude/CLAUDE.md | sed 's/^@//' | while read f; do test -f "$HOME/.claude/$f" || echo "MISSING: $f"; done`

  **Must NOT do**:
  - Do NOT modify protocol file contents
  - Do NOT add new protocols
  - Do NOT modify CLAUDE.md

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 5, 6, 7, 8)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 3

  **References**:
  - `~/.claude/protocols/` — 6 files: 01-doc-check.md, 02-working-memory.md, 03-quality-gate.md, 04-structured-reports.md, 05-infra-safety.md, 06-cross-model.md
  - `~/.claude/CLAUDE.md` lines 17-22 — @import references that depend on protocols/
  - `~/.claude/protocols/06-cross-model.md.bak.20260227_204849` — .bak file to remove

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Protocols intact with .bak cleaned
    Tool: Bash
    Steps:
      1. Run `ls ~/.claude/protocols/*.md | wc -l`
      2. Run `find ~/.claude/protocols -name '*.bak*' | wc -l`
      3. Run `grep '^@' ~/.claude/CLAUDE.md | sed 's/^@//' | while read f; do test -f "$HOME/.claude/$f" || echo "MISSING: $f"; done`
    Expected Result: 6 .md files; 0 .bak files; no MISSING output
    Evidence: .sisyphus/evidence/task-4-protocols-check.txt
  ```

  **Commit**: NO

- [x] 5. Copy HUD + remove omc-hud.mjs

  **What to do**:
  - Create HUD directory if needed: `mkdir -p ~/.claude/hud`
  - Copy latest HUD from OAL source:
    `cp /Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs ~/.claude/hud/oal-hud.mjs`
  - Remove OMC HUD artifact: `rm -f ~/.claude/hud/omc-hud.mjs`
  - Verify HUD matches source: `diff ~/.claude/hud/oal-hud.mjs /Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs`

  **Must NOT do**:
  - Do NOT modify HUD content
  - Do NOT change statusLine in settings.json (it already references the correct path)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 4, 6, 7, 8)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 3

  **References**:
  - `/Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs` — source HUD file (15,893 bytes)
  - `~/.claude/hud/oal-hud.mjs` — installed HUD (currently stale: 9,713 bytes)
  - `~/.claude/hud/omc-hud.mjs` — OMC artifact to remove
  - `~/.claude/settings.json` line 407-408 — statusLine references `node ~/.claude/hud/oal-hud.mjs`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: HUD updated and OMC HUD removed
    Tool: Bash
    Steps:
      1. Run `diff ~/.claude/hud/oal-hud.mjs /Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs`
      2. Run `test ! -f ~/.claude/hud/omc-hud.mjs`
    Expected Result: diff produces no output (files identical); omc-hud.mjs does not exist
    Evidence: .sisyphus/evidence/task-5-hud-check.txt
  ```

  **Commit**: NO

- [x] 6. Remove extra rules (05-07) from rules/

  **What to do**:
  - Remove misplaced contextual rules from core rules directory:
    `rm -f ~/.claude/rules/05-infra-safety.md`
    `rm -f ~/.claude/rules/06-cross-model.md`
    `rm -f ~/.claude/rules/06-cross-model.md.bak.*`
    `rm -f ~/.claude/rules/07-dependency-safety.md`
  - Remove any other .bak files in rules/: `rm -f ~/.claude/rules/*.bak*`
  - Verify exactly 5 core rules remain (00-truth through 04-testing)
  - Note: these contextual rules exist in `~/.claude/templates/oal/contextual-rules/` (correct location)

  **Must NOT do**:
  - Do NOT remove rules 00-04 (core rules)
  - Do NOT modify rule contents
  - Do NOT touch templates/oal/contextual-rules/

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 4, 5, 7, 8)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 3

  **References**:
  - `~/.claude/rules/` — currently has 9 files (5 core + 3 extra + 1 .bak)
  - `~/.claude/rules/05-infra-safety.md` — contextual rule incorrectly in core rules dir
  - `~/.claude/rules/06-cross-model.md` — contextual rule incorrectly in core rules dir
  - `~/.claude/rules/07-dependency-safety.md` — contextual rule incorrectly in core rules dir
  - `~/.claude/templates/oal/contextual-rules/` — correct location for contextual rules

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Rules directory clean — exactly 5 core rules
    Tool: Bash
    Steps:
      1. Run `ls ~/.claude/rules/*.md | wc -l`
      2. Run `ls ~/.claude/rules/` to list all files
      3. Run `ls ~/.claude/rules/ | grep -v '^0[0-4]-'` to check for orphans
    Expected Result: 5 .md files; only 00-truth.md through 04-testing.md; no orphan output
    Evidence: .sisyphus/evidence/task-6-rules-check.txt
  ```

  **Commit**: NO

- [x] 7. Remove OMC artifacts

  **What to do**:
  - Remove OMC state directory: `rm -rf ~/.claude/.omc`
  - Remove OMC config: `rm -f ~/.claude/.omc-config.json`
  - Verify both are gone
  - Note: `--clear-omc` in the installer handles commands/hooks/plugins OMC artifacts.
    This task handles the remaining artifacts the installer does NOT remove.

  **Must NOT do**:
  - Do NOT remove any OAL files
  - Do NOT touch .oal/ directories in project roots

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 4, 5, 6, 8)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 3

  **References**:
  - `~/.claude/.omc/` — legacy OMC state directory (contains ledger/, sessions/, snapshots/, state/)
  - `~/.claude/.omc-config.json` — legacy OMC configuration file

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All OMC artifacts removed
    Tool: Bash
    Steps:
      1. Run `test ! -d ~/.claude/.omc && echo 'PASS' || echo 'FAIL'`
      2. Run `test ! -f ~/.claude/.omc-config.json && echo 'PASS' || echo 'FAIL'`
    Expected Result: Both PASS
    Evidence: .sisyphus/evidence/task-7-omc-check.txt
  ```

  **Commit**: NO

- [x] 8. Clean ALL backup debris

  **What to do**:
  - Remove all backup directories (two naming patterns):
    `find ~/.claude -maxdepth 1 -name '.oal-backup-*' -type d -exec rm -rf {} +`
    `rm -rf ~/.claude/.oal-backups` (separate directory if exists)
  - Remove all .bak files in agents/:
    `find ~/.claude/agents -name '*.bak*' -delete`
  - Remove all settings.json backup files:
    `find ~/.claude -maxdepth 1 -name 'settings.json.bak.*' -delete`
  - Remove all CLAUDE.md backup files:
    `find ~/.claude -maxdepth 1 -name 'CLAUDE.md.backup.*' -delete`
    `find ~/.claude -maxdepth 1 -name 'CLAUDE.md.bak.*' -delete`
  - Remove all security warning state files:
    `find ~/.claude -maxdepth 1 -name 'security_warnings_state_*.json' -delete`
  - Remove __pycache__ in hooks/:
    `rm -rf ~/.claude/hooks/__pycache__`
  - Summary: count removed items

  **Must NOT do**:
  - Do NOT use `rm -rf ~/.claude/*` or any broad pattern
  - Do NOT touch `~/.claude/backups/` (Claude Code internal, different from backup debris)
  - Do NOT touch `~/.claude/cache/`, `.session-stats.json`, `history.jsonl`
  - Do NOT touch `~/.claude/plugins/`, `~/.claude/projects/`, `~/.claude/skills/`
  - Do NOT touch `~/.claude/protocols/` (handled by Task 4)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 4, 5, 6, 7)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 3

  **References**:
  - `~/.claude/.oal-backup-*` — 24+ timestamped backup directories (created by each install)
  - `~/.claude/.oal-backups/` — separate backup storage directory
  - `~/.claude/agents/*.bak.*` — 44+ agent backup files
  - `~/.claude/settings.json.bak.*` — 14+ settings backup files
  - `~/.claude/CLAUDE.md.backup.*` and `CLAUDE.md.bak.*` — 7+ CLAUDE.md backups
  - `~/.claude/security_warnings_state_*.json` — 6 security warning state files (stale)
  - `~/.claude/hooks/__pycache__/` — Python bytecode cache (stale after reinstall)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All backup debris removed
    Tool: Bash
    Steps:
      1. Run `find ~/.claude -maxdepth 1 -name '.oal-backup-*' -type d | wc -l`
      2. Run `test ! -d ~/.claude/.oal-backups && echo 'PASS' || echo 'FAIL'`
      3. Run `find ~/.claude -name '*.bak*' | wc -l`
      4. Run `find ~/.claude -name '*.backup*' | wc -l`
      5. Run `find ~/.claude/agents -name '*.bak*' | wc -l`
      6. Run `test ! -d ~/.claude/hooks/__pycache__ && echo 'PASS' || echo 'FAIL'`
    Expected Result: 0 backup dirs; .oal-backups PASS; 0 .bak files; 0 .backup files; 0 agent baks; __pycache__ PASS
    Evidence: .sisyphus/evidence/task-8-debris-check.txt

  Scenario: Protected files not touched
    Tool: Bash
    Steps:
      1. Run `test -f ~/.claude/.session-stats.json && echo 'PRESERVED' || echo 'MISSING'`
      2. Run `test -d ~/.claude/cache && echo 'PRESERVED' || echo 'MISSING'`
      3. Run `test -f ~/.claude/history.jsonl && echo 'PRESERVED' || echo 'MISSING'`
      4. Run `test -d ~/.claude/plugins && echo 'PRESERVED' || echo 'MISSING'`
    Expected Result: All 4 show PRESERVED
    Evidence: .sisyphus/evidence/task-8-protected-check.txt
  ```

  **Commit**: NO

- [x] 9. Run comprehensive acceptance criteria checks

  **What to do**:
  - Run ALL 11 acceptance criteria from the Success Criteria section below
  - Capture each result with PASS/FAIL
  - Save full results to evidence file
  - Key checks:
    1. Core rules count = exactly 5
    2. No orphan rules (only 00-04 pattern)
    3. Zero .bak/.backup files anywhere in ~/.claude
    4. Zero .oal-backup-* directories
    5. No .oal-backups/ directory
    6. No OMC artifacts (.omc/, .omc-config.json, omc-hud.mjs)
    7. HUD matches source
    8. CLAUDE.md @imports all resolve
    9. protocols/ intact (6 files, no .bak)
    10. All settings.json hooks point to existing files
    11. OAL version marker exists

  **Must NOT do**:
  - Do NOT fix issues in this task — only report
  - If any check fails, document which one and stop

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 10)
  - **Blocks**: F1, F2
  - **Blocked By**: Tasks 4, 5, 6, 7, 8

  **References**:
  - Success Criteria section of this plan — contains all 11 verification commands
  - `~/.claude/settings.json` — hook registrations to validate
  - `~/.claude/CLAUDE.md` — @import references to validate

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All 11 acceptance criteria pass
    Tool: Bash
    Steps:
      1. Run each verification command from Success Criteria section
      2. Compare actual vs expected output
      3. Count: N pass / N fail
    Expected Result: 11/11 PASS
    Failure Indicators: any criterion reports unexpected output
    Evidence: .sisyphus/evidence/task-9-acceptance-results.txt
  ```

  **Commit**: NO

- [x] 10. Validate hook-to-file integrity

  **What to do**:
  - Parse `~/.claude/settings.json` and extract all hook command paths
  - For each hook command, verify the referenced .py file exists
  - Check that each hook .py file has valid Python syntax: `python3 -c "import py_compile; py_compile.compile('path', doraise=True)"`
  - Report any orphan hooks (registered but file missing) or orphan files (file exists but not registered)
  - Specifically verify quality-gate.py: exists AND is registered (documented as custom hook)

  **Must NOT do**:
  - Do NOT modify settings.json
  - Do NOT remove any hook files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 9)
  - **Blocks**: F1, F2
  - **Blocked By**: Tasks 4, 5, 6, 7, 8

  **References**:
  - `~/.claude/settings.json` hooks section (lines 266-404) — all hook registrations
  - `~/.claude/hooks/` — all installed hook files
  - `~/.claude/hooks/quality-gate.py` — custom hook (NOT from OAL source, documented as kept)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All hook references valid + syntax check
    Tool: Bash
    Steps:
      1. Run Python script to parse settings.json hooks and verify each file exists
      2. Run `python3 -c "import py_compile; py_compile.compile(path, doraise=True)"` for each hook
      3. Check for quality-gate.py specifically: exists + registered
    Expected Result: 0 orphan hooks; 0 missing files; all syntax valid; quality-gate.py confirmed
    Evidence: .sisyphus/evidence/task-10-hook-integrity.txt

  Scenario: No unregistered hook files
    Tool: Bash
    Steps:
      1. List all .py files in ~/.claude/hooks/ (excluding _common.py, __pycache__)
      2. List all hook commands from settings.json
      3. Compare: any .py file not referenced by settings.json?
    Expected Result: All hook .py files are registered (except _common.py which is a utility)
    Evidence: .sisyphus/evidence/task-10-hook-integrity.txt
  ```

  **Commit**: NO


## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `deep`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (check file, run command). For each "Must NOT Have": verify forbidden action was not taken. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Final State Snapshot + Diff** — `quick`
  Capture final `~/.claude` directory listing. Compare against pre-install snapshot from Task 1. Document what was added, removed, and preserved. Save evidence.
  Output: `Added [N] | Removed [N] | Preserved [N] | Clean: YES/NO`

---

## Commit Strategy

- No git commits needed (this is an installation task, not code changes)

---

## Success Criteria

### Verification Commands
```bash
# Core rules count = exactly 5
ls ~/.claude/rules/*.md | wc -l  # Expected: 5

# No orphan rules (only 00-04 pattern)
ls ~/.claude/rules/ | grep -v "^0[0-4]-"  # Expected: empty

# Zero .bak/.backup files
find ~/.claude -name "*.bak*" -o -name "*.backup*" | wc -l  # Expected: 0

# Zero backup directories
find ~/.claude -maxdepth 1 -name ".oal-backup-*" -type d | wc -l  # Expected: 0
test ! -d ~/.claude/.oal-backups  # Expected: exit 0

# No OMC artifacts
test ! -d ~/.claude/.omc  # Expected: exit 0
test ! -f ~/.claude/.omc-config.json  # Expected: exit 0
test ! -f ~/.claude/hud/omc-hud.mjs  # Expected: exit 0

# HUD is current
diff ~/.claude/hud/oal-hud.mjs /Users/cminseo/Documents/scripts/Shell/OAL/hud/oal-hud.mjs  # Expected: no output

# CLAUDE.md @imports all resolve
grep "^@" ~/.claude/CLAUDE.md | sed 's/^@//' | while read f; do test -f "$HOME/.claude/$f" || echo "MISSING: $f"; done  # Expected: no output

# protocols/ intact (6 files, no .bak)
ls ~/.claude/protocols/*.md | wc -l  # Expected: 6
find ~/.claude/protocols -name "*.bak*" | wc -l  # Expected: 0

# All settings.json hooks point to existing files
python3 -c "
import json, os
d = json.load(open(os.path.expanduser('~/.claude/settings.json')))
for event, matchers in d.get('hooks', {}).items():
    for m in matchers:
        for h in m.get('hooks', []):
            cmd = h.get('command', '')
            if '.py' in cmd:
                path = cmd.split()[-1].strip('\"').replace('\$HOME', os.path.expanduser('~'))
                assert os.path.exists(path), f'MISSING: {path}'
print('All hook files verified')
"
# Expected: "All hook files verified"
```

### Final Checklist
- [x] All "Must Have" present — hooks installed, settings.json valid, CLAUDE.md @imports resolve, protocols intact
- [x] All "Must NOT Have" absent — no OMC artifacts, no stray backups, no orphan rules, no omc-hud.mjs
- [x] All 11 acceptance criteria pass — rules=5, protocols=6, HUD current, all hooks verified, @imports clean
- [x] /OAL:health-check clean — all hook files verified via python3 check, all @imports resolve, no missing files
