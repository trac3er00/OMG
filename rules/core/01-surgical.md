# Rule 01 — Surgical Changes & Active Planning

## Change Budgets
- **Bugfix / small:** ≤3 files OR ≤120 LOC
- **Medium:** ≤8 files OR ≤400 LOC (set CHANGE_BUDGET=medium)
- **Large:** explicit justification required

## Refactor Ladder (smallest safe step first)
1. Minimal fix in place
2. Local refactor in same module
3. Extract helper only if reused ≥2 places
4. Cross-module refactor only with plan approval

## Active Planning
For 3+ file changes: create .oal/state/_plan.md + _checklist.md BEFORE coding.
Mark [x] immediately as steps complete. Update plan when approach changes.
If stuck 2x: STOP. Try different approach or /OAL:escalate.

> Enforced: stop-gate.py checks diff budget. circuit-breaker.py catches loops.
