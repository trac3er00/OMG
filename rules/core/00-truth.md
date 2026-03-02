# Rule 00 — Truth & Evidence

NEVER claim a state you haven't verified. Period.

**Before saying "done/fixed/works/passes":**
1. Run the verification command
2. Check exit code = 0
3. Include evidence in your report

**Report format (every completion):**
- **Verified:** [commands run + exit codes]
- **Unverified:** [what couldn't be tested + why]
- **Assumptions:** [what you assumed without checking]

**If tests not run:** Say "Tests: NOT RUN (reason: ...)"
**If tests fail:** Show failing command + output + plan to fix

Forbidden without evidence: "done", "LGTM", "fixed", "works now", "tests passed"

> Enforced: stop-gate.py checks evidence. tool-ledger.py logs tool calls.
