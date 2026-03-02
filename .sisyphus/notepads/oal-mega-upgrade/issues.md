# OAL Mega-Upgrade Issues

## [2026-02-28] Known Issues to Fix

### CRITICAL: stop_hook_active bug
- File: hooks/stop-gate.py
- Problem: stop_hook_active boolean from Stop payload is NEVER checked
- Risk: Infinite loop when Claude Code calls stop hook recursively
- Fix: Add guard at TOP of file (after JSON parse, before CHECK 1)

### Existing hook count discrepancy
- README says 15 hooks, actual count is 18
- 3 undercounted: config-guard.py, policy_engine.py, shadow_manager.py

### circuit-breaker normalization
- Pattern keys not normalized (npm test ≠ npm run test)
- Fix in Wave 2 Task 14
