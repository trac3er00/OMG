# Context Minimization Principle

Based on: ETH Zurich (2026) "Evaluating AGENTS.md" (arXiv:2602.11988)
and Lulla et al. (2026) "On the Impact of AGENTS.md Files" (arXiv:2601.20404)

## Key Findings
- LLM-generated context files LOWER success rates and INCREASE cost by 20%+
- Human-written minimal files may help slightly (+4%) if they contain ONLY
  information the agent cannot discover by reading project files
- Always-on rules that don't vary by task type cause unnecessary work

## OMG Policy: Non-Discoverable Only

### INJECT (agent can't discover this from code):
- Project conventions (naming, commit style, PR process)
- AI behavior preferences (language, communication style)
- Active task state (working memory, checklist progress)
- Failure history (what approaches already failed)
- Team decisions (why X was chosen over Y)

### DO NOT INJECT (agent can discover this by reading code):
- Language and framework (detectable from package.json, Cargo.toml, etc.)
- Dependencies list (detectable from lockfiles)
- Directory structure (detectable from file listing)
- API shapes (detectable from source code)
- Database schema (detectable from migrations/models)

### Budget Enforcement
- session-start: ≤1500 chars total
- prompt-enhancer: ≤800 chars per prompt
- handoff: ≤60 lines, portable ≤100 lines
- Stale handoffs (>48h): auto-skipped
