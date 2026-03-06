# Rule 02 — Circuit Breaker & Collaborative Solving

## 2-Strike Rule
Same approach fails twice → STOP. Don't retry with slight variation.

Options:
1. Fundamentally different approach
2. /OMG:escalate codex (for deep debugging)
3. /OMG:escalate gemini (for UI/visual issues)
4. Ask the user

## Anti-Patterns (NEVER)
- **Bulldozer:** Same approach with slight variation → fails → retry harder
- **Lone Wolf:** 10 failed attempts before asking for help
- **Assumer:** Build [X] without confirming user wants [X]
- **Force-Fixer:** Immediately try to fix without understanding root cause

## Auto-Escalation
After 3 failures: circuit-breaker.ts suggests /OMG:escalate with specific context.
After 5 failures: HARD BLOCK. Must escalate or get user input.

> Enforced: circuit-breaker.ts tracks patterns + auto-escalates.
