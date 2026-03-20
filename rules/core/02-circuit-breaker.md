# Rule 02 — Circuit Breaker & Collaborative Solving

## 2-Strike Rule
Same approach fails twice → STOP. Don't retry with slight variation.

Use `AskUserQuestion` to present options (never plain text):
- question: "Same approach failed twice. How should we proceed?"
- header: "Stuck"
- options:
  - label: "Different approach", description: "Try a fundamentally different strategy"
  - label: "Escalate to Codex", description: "Deep debugging and root cause analysis"
  - label: "Escalate to Gemini", description: "UI/visual issue review"
  - label: "Ask user", description: "Get guidance on how to proceed"

## Anti-Patterns (NEVER)
- **Bulldozer:** Same approach with slight variation → fails → retry harder
- **Lone Wolf:** 10 failed attempts before asking for help
- **Assumer:** Build [X] without confirming user wants [X]
- **Force-Fixer:** Immediately try to fix without understanding root cause

## Auto-Escalation
After 3 failures: circuit-breaker.py emits `@@ASK_USER_OPTIONS@@` — use AskUserQuestion to present escalation choices.
After 5 failures: HARD BLOCK. Must use AskUserQuestion to get user direction before any further action.

> Enforced: circuit-breaker.py tracks patterns + auto-escalates.
