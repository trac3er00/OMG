# Issues — compact-overhaul

## [2026-03-01] Atlas: Known issues to fix

1. `test-validator.py` missing `should_skip_stop_hooks()` — biggest deadlock contributor
2. Guard 3 in `_common.py` is dead code — `stop_reason`/`end_turn_reason` fields don't exist in Stop hook payloads
3. `.stop-block-tracker.json` has cross-session race conditions — needs `session_id` field
4. 3 separate Stop hook groups in `~/.claude/settings.json` run in parallel — any single group blocking causes deadlock
5. Pre-compact truncates handoff at 60 lines — too short for complex sessions
6. `quality-gate.py` at `~/.claude/hooks/` is a separate Stop hook group — must be absorbed into stop_dispatcher.py before consolidation


## F4 Findings (2026-03-01 00:41:43)
- Task 1 missing should_skip guard in `hooks/test-validator.py`.
- Task 3 incomplete: `record_stop_block()` callers in `hooks/stop_dispatcher.py` do not pass `reason`.
- Task 5 missing entirely: no `check_bare_done()` in `hooks/stop_dispatcher.py` while `~/.claude/hooks/quality-gate.py` is deleted.
- Task 7 incomplete: required stderr diagnostics missing in `hooks/stop_dispatcher.py` and `hooks/test-validator.py`.
- Task 8 partial: failure tracker output in `hooks/pre-compact.py` lacks approach/last_error details; active plan section not implemented as spec.
- Task 10 partial: `hooks/session-start.py` does not inject full handoff content (extracts/truncates sections).
- Task 11 incomplete: no `.oal/state/.auto-handoff-requested` signal write.
- Task 12 incomplete: planning gate demotion does not also check `is_stop_block_loop()`.
- Task 13 incomplete: quality-runner skip lacks `is_stop_block_loop()` path and does not apply when invoked via dispatcher callable.
