# Learnings — compact-overhaul

## [2026-03-01] Atlas: Pre-execution research

### File Locations
- `hooks/test-validator.py` — Stop hook, does NOT call `should_skip_stop_hooks()` — biggest deadlock contributor
- `hooks/_common.py` — Shared utilities. Guard 3 (lines ~276-298) is dead code. `record_stop_block()` at ~364, `is_stop_block_loop()` at ~385
- `hooks/stop_dispatcher.py` — Main stop orchestrator. Calls `should_skip_stop_hooks()` at top. `record_stop_block()` called at ~680, ~686, ~713
- `hooks/pre-compact.py` — Truncates handoff at 60 lines (line ~112-113), portable at 100 lines (line ~121-122)
- `hooks/quality-runner.py` — Already calls `should_skip_stop_hooks()` — use as pattern for test-validator.py
- `hooks/session-start.py` — Injects handoff context. Handoff injection at section 4 (~line 120+)
- `~/.claude/hooks/quality-gate.py` — EXISTS (102 lines). Bare-done detection. Must be absorbed into stop_dispatcher.py before deletion
- `~/.claude/settings.json` — 3 separate Stop hook groups (quality-gate.py, test-validator.py+quality-runner.py, stop_dispatcher.py)

### Key Constants
- `_BLOCK_LOOP_THRESHOLD = 2` — Guard 4 triggers on 3rd block (count >= 2)
- `_BLOCK_LOOP_WINDOW_SECS = 30` — Window for loop detection
- Stop hook timeout after consolidation: 90s (quality-runner needs 60s subprocess)
- Handoff truncation: raise 60→120 lines, portable 100→150 lines
- Context pressure threshold: 150 tool calls

### Critical Pattern (Task 1)
Copy from quality-runner.py lines 15-25:
```python
from _common import _resolve_project_dir, should_skip_stop_hooks
...
data = json.load(sys.stdin)
if should_skip_stop_hooks(data):
    sys.exit(0)
```

### Guard 3 Dead Code Location
In `_common.py` `should_skip_stop_hooks()`:
- `_CONTEXT_PATTERNS` list — REMOVE
- `_RATE_LIMIT_PATTERNS` list — REMOVE  
- The for loop checking `stop_reason`/`end_turn_reason` against these patterns — REMOVE
- BUT: keep the `stop_reason` and `end_turn_reason` variable assignments (Guard 5 uses them)

### Stop Block Tracker Path
`.omg/state/ledger/.stop-block-tracker.json`

### Not a git repo
Working directly in project dir. No git worktree isolation.

### Python Import Caveat
`test-validator.py`, `quality-runner.py`, `prompt-enhancer.py` have hyphens — NOT directly importable as Python modules. Use `importlib.import_module()` or create `context_pressure.py` (underscore-named) as shared module.


## F4 Scope Fidelity Audit (2026-03-01 00:41:43)
- Verified full 1201-line plan against implementation files directly (no git available).
- Most failures are integration gaps between tasks, not syntax/runtime errors.
- Critical coupling observed: Task 5 (bare-done absorption) missing, but Task 6 removed quality-gate hook anyway.
