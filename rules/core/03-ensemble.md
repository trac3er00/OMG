# Rule 03 — Ensemble Collaboration

## Who Does What
- **Claude:** Orchestration, synthesis, integration, user communication
- **Codex:** Backend logic, security audit, root cause, algorithms, deep debugging
- **Gemini:** UI/UX review, visual comparison, accessibility, responsive design

## When to Delegate (DO IT, don't just think about it)
- Backend bug persists after 2 attempts → /OMG:escalate codex
- Security/auth/crypto involved → /OMG:escalate codex
- UI/visual change made → /OMG:escalate gemini
- Change spans frontend + backend → /OMG:ccg (tri-model)
- Stuck on anything for 3+ attempts → /OMG:escalate to relevant model

## Auto-Detection
prompt-enhancer.ts detects keywords and suggests the right model.
circuit-breaker.ts auto-suggests escalation after failures.

## Plugins & MCPs
- Installed plugins: USE them (they're installed for a reason)
- Available MCPs: SUGGEST with reasoning, wait for user confirmation
- Context7 (if available): Use for up-to-date library docs

## Natural Communication
Say: "This touches auth — let me get Codex to check the security."
NOT: "Invoking cross-model review protocol for backend analysis."

> Enforced: prompt-enhancer.ts + session-start.ts detect available tools.
