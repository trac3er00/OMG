# OAL Mega-Upgrade: All-In-One Plugin Transformation

## TL;DR

> **Quick Summary**: Transform OAL into the definitive Claude Code All-In-One plugin by absorbing the best features from 9 competing plugins (Superpowers, Ralph Wiggum, claude-flow, claude-mem, memsearch, Beads, planning-with-files, hooks-mastery, compound-engineering) while fixing existing bugs, adding specialized agent roles with model-per-agent routing (gemini-cli for frontend/visual, codex-cli for backend/logic), and maintaining an on-demand/lazy architecture that injects zero context unless triggered.
> 
> **Deliverables**:
> - True Ralph autonomous loop via Stop hook blocking
> - Lightweight cross-session memory (memsearch-style, plain .md)
> - Planning enforcement with forced re-read + completion gate
> - 9 new agents (6 domain + 3 cognitive modes) with model-per-agent routing
> - Compound learning capture system
> - Model-per-agent dispatch (gemini-cli ↔ frontend, codex-cli ↔ backend/security)
> - All existing bug fixes
> - pytest test infrastructure
> - Token budget optimization
> - On-demand/lazy architecture (zero context unless triggered)
> 
> **Estimated Effort**: XL (48 tasks across 7 waves)
> **Parallel Execution**: YES — 7 waves, max 8 concurrent agents
> **Critical Path**: Wave 0 (Foundation) → Wave 1 (Multiplexer) → Waves 2-5 (Core Features) → Wave 6 (Final)

---

## Context

### Original Request
Transform OAL into an All-In-One Claude Code plugin by:
1. Analyzing 9+ competing plugins and absorbing their best features
2. Fixing all existing bugs in custom commands, hooks, MCP integrations
3. Making ULW/Ralph persistent loop actually work (currently keyword-only)
4. Adding specialized agent roles (frontend-designer, backend-engineer, SRE, etc.)
5. Reducing token consumption while making OAL smarter
6. Adding cross-session persistent memory
7. Adding compound learning (learn from past session mistakes)

### Interview Summary
**Key Discussions**:
- Memory strategy: memsearch-style lightweight (plain .md + `context: fork`, Stop hook capture + Haiku summary)
- Ralph loop: True Stop hook block (`{"decision":"block"}`, state file + iteration counter + `stop_hook_active` guard)
- Agent roles: 8-12 domain agents + 4-5 cognitive modes (research, architect, implement, review, debug)
- Priority: Dependency-based (what unblocks most downstream features first)
- Testing: pytest for Python hooks + agent-executed QA scenarios

**Research Findings** (10 plugins analyzed at source-code level):
- Superpowers (65.6k⭐): Anti-rationalization tables, hard gates, 1% rule, fresh-subagent-per-task
- Ralph Wiggum: Stop hook `{"decision":"block","reason":"<prompt>"}`, state file with YAML frontmatter
- claude-flow (16.3k⭐): Real DAG scheduler + Q-Learning router (but overstated "60+ agents")
- claude-mem (31.7k⭐): 3-tier memory, AI compression via SDK subprocess, ~2,400-4,200 tokens/session
- memsearch: `context: fork` pattern (memory search in isolated subagent), plain .md, ~60 tokens cold-start
- Beads: `bd ready` (only unblocked work), atomic `--claim`, AI compaction via Haiku
- planning-with-files (14.8k⭐): `head -30 task_plan.md` forced re-read, Stop hook blocks until phases complete
- hooks-mastery: 13 hook event schemas, exit code protocol, `stop_hook_active` guard, agent-level hooks
- compound-engineering (9.7k⭐): `learnings-researcher` at plan start, YAML schema solutions, `critical-patterns.md`
- everything-claude-code (54.6k⭐): 56 skills + continuous-learning-v2 instinct system

### Metis Review
**Critical Findings** (addressed in plan):
1. **`stop_hook_active` bug**: OAL's `stop-gate.py` NEVER checks this flag → latent infinite loop bug. Fix FIRST.
2. **Stop Hook Multiplexer needed**: 4+ features compete for the Stop event (Ralph, planning, evidence gate, compound learning). Need priority chain.
3. **Use `SessionEnd` for capture**: Memory/learning capture should use `SessionEnd` (fire-and-forget, no timeout risk), NOT `Stop`.
4. **Plugin Stop hooks don't block** (GitHub #10412): Hooks MUST stay in `~/.claude/settings.json`, NOT plugin manifest.
5. **18 hooks not 15**: Plan undercounted (`config-guard.py`, `policy_engine.py`, `shadow_manager.py`, `trust_review.py`).
6. **Token budget math**: Adding features increases budget ~70% unless explicitly constrained. Hard per-feature allocations required.
7. **Existing knowledge retrieval**: `prompt-enhancer.py:344-424` already has keyword-matched retrieval with `.index.json` cache. Don't duplicate.
8. **6 unused hook events**: SessionEnd, SubagentStop, PostToolUseFailure, PermissionRequest, SubagentStart, Notification.

---

## Work Objectives

### Core Objective
Absorb the best features from 9 competing Claude Code plugins into OAL's existing architecture while fixing bugs, adding specialized agents with model-per-agent routing (gemini-cli for frontend/visual, codex-cli for backend/logic/security), implementing a built-in code simplifier (anti-AI-slop), and maintaining OAL's on-demand/lazy architecture that injects zero context unless explicitly triggered.

### Concrete Deliverables
- `hooks/stop_dispatcher.py` — Stop Hook Multiplexer with priority chain
- `hooks/session-end-capture.py` — SessionEnd hook for memory + learning capture
- `hooks/pre-tool-inject.py` — PreToolUse hook for plan forced re-read
- `.oal/state/memory/` — Cross-session memory storage (plain .md files)
- `.oal/state/ralph-loop.json` — Ralph loop state file
- `.oal/knowledge/learnings/` — Compound learning storage
- `agents/` — 9 new agent definitions (6 domain + 3 cognitive) with model routing metadata
- `rules/contextual/cognitive-*.md` — 3 cognitive mode rules
- `tests/` — pytest infrastructure + hook unit tests + integration tests
- Updated `settings.json` — Feature flags, model routing table, new hook registrations
- Code simplifier (anti-AI-slop) — built into prompt-enhancer.py + stop-gate.py CHECK 7
- Model-per-agent routing table — maps domain agents → specific CLI models (gemini-cli/codex-cli)

### Definition of Done
- [x] `python3 -m pytest tests/ -x -q` → ALL PASS
- [x] All 16 acceptance criteria pass (14 Metis + 2 new: simplifier + model routing)
- [x] Token budget: session-start ≤ 2000 chars, prompt-enhancer ≤ 1000 chars
- [x] Ralph loop: can start, iterate, and cancel without infinite loop
- [x] Memory: captures session summary on end, retrieves in next session
- [x] Planning: forced re-read before tool calls, blocks completion if phases incomplete
- [x] Simplifier: stop-gate detects and warns about AI slop patterns in written files
- [x] Model routing: agent definitions include `preferred_model` metadata, dispatch uses it
- [x] On-demand: session-start injects ≤200 chars when no features are active
- [x] All existing commands work (no regressions)

### Must Have
- `stop_hook_active` bug fix (BEFORE any other Stop hook work)
- Stop Hook Multiplexer with explicit priority ordering
- Feature flags for every new feature (default: enabled)
- Hook error logging to `.oal/state/ledger/hook-errors.jsonl`
- Atomic file writes (`.tmp` + `os.rename()`) for all state files
- Memory rotation (max 50 files, prune oldest)
- Ralph escape hatch (`rm .oal/state/ralph-loop.json` or max iterations)
- All hooks exit(0) on crash (crash isolation preserved)
- Token budget hard caps per feature
- Code simplifier: enhanced `@discipline` in prompt-enhancer + CHECK 7 in stop-gate
- Model-per-agent routing: each agent .md file includes `preferred_model:` metadata
- On-demand architecture: features activate ONLY when called by user/Claude/workflow
- **Claude Code Protocol Compliance**: ALL hooks must follow exact JSON schemas per event type (see Protocol Reference)
- **Precise agent dispatch**: Agent registry maps each agent → `task()` parameters (category, load_skills, subagent_type)
- **MCP-aware agents**: Agent definitions reference available MCP tools by name when relevant
- **codex-cli/gemini-cli integration**: Model dispatch uses actual CLI subprocess calls (like OMC), not just suggest commands
- **Domain-aware circuit-breaker**: Failures in auth/security → suggest codex, UI failures → suggest gemini (not generic escalation)
- **Progressive escalation**: Circuit-breaker uses time-decay + domain context, not just failure count
- **Scope drift detection**: Stop-gate CHECK detects when agent modifies files outside planned scope
- **Pre-flight guardrails**: PreToolUse hook validates dangerous operations (deploy, migrate, delete) require explicit confirmation
- **Recovery memory**: Circuit-breaker remembers what approach worked for similar past failures

### Must NOT Have (Guardrails)
- ❌ No vector database (ChromaDB, SQLite+vectors). Plain .md files only.
- ❌ No DAG scheduler. Use `_checklist.md` with `[x]/[ ]/[!]` markers.
- ❌ No AI-powered learning synthesis in v1. Capture only, no Haiku summarization during hooks.
- ❌ No more than 9 new agents (6 domain + 3 cognitive). Total: 14 max.
- ❌ No eager-loading all agents at session start. On-demand via keyword detection.
- ❌ No Haiku API calls in Stop hook (60s timeout risk). Use SessionEnd or async.
- ❌ No web UI. No HTTP servers. No ports.
- ❌ No duplicate knowledge retrieval. Integrate with existing `prompt-enhancer.py:344-424`.
- ❌ No cross-project memory. Memory is project-scoped (`.oal/state/memory/`).
- ❌ No breaking changes to existing hook behavior without feature flag.
- ❌ Don't move hooks to plugin manifest path (GitHub #10412: plugin Stop hooks don't block).
- ❌ No always-on context injection. Session-start must be ≤200 chars when no features are active.
- ❌ No simplifier BLOCKING — CHECK 7 is ADVISORY only (stderr), never blocks completion.
- ❌ No model routing that requires API keys or external config — metadata only, CLI dispatch.
- ❌ No guardrails that LIMIT developer velocity — all guardrails must ENABLE (suggest better path, not just block).

---

### Claude Code Protocol Reference (MANDATORY for all new hooks/agents)

```
HOOK EVENTS — Exact stdin/stdout JSON contracts:

SessionStart:
  stdin:  {session_id, cwd, is_compact, ...}
  stdout: {contextInjection: string}  ← injected into Claude's context

UserPromptSubmit:
  stdin:  {tool_input: {user_message: string}, ...}
  stdout: {contextInjection: string}

PreToolUse:
  stdin:  {tool_name: string, tool_input: {...}, session_id: string}
  stdout: {hookSpecificOutput: {hookEventName:"PreToolUse", permissionDecision:"allow"|"deny", permissionDecisionReason:string}}
  stdout: {contextInjection: string}  ← OR inject context instead of allow/deny

PostToolUse:
  stdin:  {tool_name, tool_input, tool_response, session_id}
  stdout: {contextInjection: string}  ← optional follow-up context

Stop:
  stdin:  {stop_hook_active: bool, ...}
  stdout: {decision: "block", reason: string}  ← blocks completion
  stdout: (empty)  ← allows completion

SessionEnd:
  stdin:  {session_id, cwd, duration_ms}
  stdout: (ignored — fire-and-forget)

PostToolUseFailure:
  stdin:  {tool_name, error, session_id}
  stdout: {contextInjection: string}

EXIT CODES:
  exit(0) = success (hook ran, output is valid)
  exit(1) = error (logged, hook skipped)
  exit(2) = deny/block (PreToolUse only, in some implementations)

AGENT .md FORMAT:
  Standard markdown with YAML frontmatter:
  ---
  name: agent-name
  model: claude-sonnet-4-20250514  # or leave blank for default
  ---
  # Agent Name
  You are [role description]...
  ## Available Tools: [list of tools this agent should prefer]
  ## Constraints: [what this agent must NOT do]

COMMAND .md FORMAT:
  Standard markdown. First line = description.
  Claude reads the file content as instructions when user types /command-name.

task() DISPATCH PARAMETERS:
  task(category="quick|deep|ultrabrain|visual-engineering|unspecified-high|...",
       load_skills=["skill-name"],
       subagent_type="explore|librarian|oracle|metis|momus",
       prompt="...",
       run_in_background=true|false)

MODEL ROUTING via CLI:
  codex-cli: Bash invocation with structured prompt, captures stdout
  gemini-cli: Bash invocation with structured prompt, captures stdout
  Detection: which codex 2>/dev/null && echo 'available'
  Env override: CLAUDE_CODE_SUBAGENT_MODEL=haiku (for cost-aware routing)
```

### Guardrail Architecture (STRONG, feature-rich, NOT limiting)

```
CIRCUIT-BREAKER v2 (Enhanced):
  Phase 1 (count=1): Log failure, no action
  Phase 2 (count=2): Suggest alternative approach in context
  Phase 3 (count=3): Domain-aware escalation:
    └ auth/security/crypto failure → 'Try /OAL:escalate codex'
    └ UI/CSS/layout failure      → 'Try /OAL:escalate gemini'
    └ logic/algorithm failure     → 'Try /OAL:escalate codex'
    └ unknown domain             → 'Try different approach or ask user'
  Phase 4 (count=5): HARD BLOCK — must escalate, change approach, or get user input
  Time-decay: Failures older than 30 minutes count as half-weight
  Recovery memory: On success, store 'what worked' in .oal/state/ledger/recovery.jsonl
  On similar future failure, suggest the recovery approach first

SCOPE DRIFT DETECTION (stop_dispatcher CHECK 8):
  If _plan.md or _checklist.md exists:
    Extract planned file paths from plan
    Compare git diff --name-only against planned paths
    If >30% of changed files are NOT in plan → advisory:
      'Scope drift: N files changed outside plan. Review before completing.'
  Always advisory, never blocking.

PRE-FLIGHT GUARDRAILS (pre-tool-inject.py):
  PreToolUse checks for dangerous patterns:
    - Bash(rm -rf *) → deny with reason
    - Bash(git push --force) → deny unless explicit flag
    - Bash(*deploy*|*migrate*) → inject confirmation prompt
    - Write/Edit to .env* → deny (already in firewall, reinforce)
  These SUPPLEMENT existing firewall.py and secret-guard.py.

EVIDENCE CHAIN:
  Every block decision includes:
    - What was expected (from plan/checklist)
    - What actually happened (from ledger/git)
    - What to do next (actionable suggestion, not just 'fix it')
  Every advisory includes:
    - Severity (info/warning/critical)
    - Specific file:line reference where issue found
    - Suggested fix command or approach
```

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (setting up)
- **Automated tests**: YES — pytest for hooks + agent-executed QA
- **Framework**: pytest (Python hooks are the primary codebase)
- **Pattern**: Each task includes both pytest unit tests AND agent-executed QA scenarios

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Hook testing**: Use Bash — pipe JSON to hook script, assert stdout/exit code
- **Integration testing**: Use Bash — simulate full hook lifecycle with state files
- **Agent testing**: Use Bash — verify agent .md files load correctly
- **Token budget testing**: Use Bash — measure output length, assert within limits

### Acceptance Criteria (from Metis — all executable)
```bash
# AC1: Memory capture on SessionEnd
echo '{"hook_event_name":"SessionEnd","session_id":"test","cwd":"/tmp"}' | python3 hooks/session-end-capture.py && ls .oal/state/memory/*.md | wc -l  # Assert: ≥ 1

# AC2: Memory retrieval in session-start
echo '{}' | python3 hooks/session-start.py | python3 -c "import sys,json; d=json.load(sys.stdin); assert '@memory' in d.get('contextInjection','')"

# AC3: Memory within token budget
echo '{}' | python3 hooks/session-start.py | python3 -c "import sys; assert len(sys.stdin.read()) <= 2200"

# AC4: Corrupted memory graceful degradation
echo "CORRUPTED{{{{" > .oal/state/memory/test.md && echo '{}' | python3 hooks/session-start.py; echo $?  # Assert: 0

# AC5: stop_hook_active guard prevents infinite loop
echo '{"stop_hook_active":true}' | python3 hooks/stop-gate.py; echo $?  # Assert: 0, NO block

# AC6: Ralph blocks when iteration needed
echo '{}' > .oal/state/ralph-loop.json && echo '{"stop_hook_active":false}' | python3 hooks/stop-gate.py | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('decision')=='block'"

# AC7: Ralph respects max iterations
echo '{"iteration":50,"max_iterations":50}' > .oal/state/ralph-loop.json && echo '{"stop_hook_active":false}' | python3 hooks/stop-gate.py | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('decision','')!='block'"

# AC8: Agent keyword routing
echo '{"tool_input":{"user_message":"fix the auth vulnerability"}}' | python3 hooks/prompt-enhancer.py | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'security' in d.get('contextInjection','').lower()"

# AC9: Agent context within budget
echo '{"tool_input":{"user_message":"implement full stack feature"}}' | python3 hooks/prompt-enhancer.py | python3 -c "import sys; assert len(sys.stdin.read()) <= 1200"

# AC10: Session-start total ≤ 2000 chars
echo '{}' | python3 hooks/session-start.py | python3 -c "import sys; assert len(sys.stdin.read()) <= 2200"

# AC11: Prompt-enhancer total ≤ 1000 chars
echo '{"tool_input":{"user_message":"crazy implement auth"}}' | python3 hooks/prompt-enhancer.py | python3 -c "import sys; assert len(sys.stdin.read()) <= 1200"

# AC12: All tests pass
python3 -m pytest tests/ -x -q  # Assert: exit 0

# AC13: Hook crash isolation
echo 'INVALID' | python3 hooks/stop-gate.py; echo $?  # Assert: 0

# AC14: Feature flags respected
OAL_MEMORY_ENABLED=0 echo '{}' | python3 hooks/session-start.py | python3 -c "import sys,json; d=json.load(sys.stdin); assert '@memory' not in d.get('contextInjection','')"
```

# AC15: Simplifier detects AI slop (advisory)
echo '{"tool_input":{"user_message":"implement auth"}}' | python3 hooks/prompt-enhancer.py | python3 -c "import sys,json; d=json.load(sys.stdin); ci=d.get('contextInjection',''); assert 'noise comment' in ci.lower() or 'clean' in ci.lower() or 'minimal' in ci.lower()"

# AC16: Model routing metadata in agent files
grep -l 'preferred_model:' agents/*.md | wc -l  # Assert: ≥ 9 (all new agents have model metadata)

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (Start Immediately — foundation, MAX PARALLEL):
├── Task 1:  Fix stop_hook_active bug in stop-gate.py [quick]
├── Task 2:  Add hook error logging to _common.py [quick]
├── Task 3:  Add feature flags system to _common.py + settings.json [quick]
├── Task 4:  Create token budget allocation constants [quick]
├── Task 5:  Set up pytest infrastructure [quick]
├── Task 6:  Write baseline hook tests [unspecified-high]
└── Task 7:  Create shared test helpers [quick]

Wave 1 (After Wave 0 — Stop Hook Multiplexer, CRITICAL PATH):
├── Task 8:  Refactor stop-gate.py → stop_dispatcher.py [deep]
├── Task 9:  Create SessionEnd capture hook skeleton [unspecified-high]
├── Task 10: Add PostToolUseFailure hook for failure tracking [quick]
└── Task 11: Create PreToolUse plan injection hook [unspecified-high]

Wave 2 (After Wave 0 — Bug Fixes + Quality, PARALLEL with Wave 1):
├── Task 12: Fix command routing bugs (OAL:crazy, OAL:deep-plan) [unspecified-high]
├── Task 13: Fix prompt-enhancer stuck detection + dedup [unspecified-high]
├── Task 14: Fix circuit-breaker pattern normalization [quick]
├── Task 15: Fix CCG/Teams Python CLI integration [unspecified-high]
├── Task 16: Fix knowledge retrieval .index.json corruption [quick]
└── Task 17: Implement code simplifier (anti-AI-slop) [unspecified-high]  ← NEW

Wave 3 (After Waves 1+2 — Core Features, MAX PARALLEL):
├── Task 18: Implement Ralph true loop (state file + block logic) [deep]
├── Task 19: Implement memory capture on SessionEnd [deep]
├── Task 20: Implement memory storage format + rotation [unspecified-high]
├── Task 21: Implement planning enforcement (forced re-read) [unspecified-high]
├── Task 22: Implement planning completion gate [unspecified-high]
├── Task 23: Create agent registry with model routing metadata [unspecified-high]
└── Task 24: Create 6 domain agent definitions + 3 cognitive agents [quick]

Wave 4 (After Wave 3 — Integration + Polish):
├── Task 25: Ralph prompt injection + escape hatch [deep]
├── Task 26: Memory retrieval via context:fork skill [deep]
├── Task 27: Memory integration into session-start.py [unspecified-high]
├── Task 28: Create 3 cognitive mode rules + /OAL:mode command [unspecified-high]
├── Task 29: Add agent routing + model dispatch to prompt-enhancer.py [unspecified-high]
├── Task 30: Implement compound learning capture on SessionEnd [unspecified-high]
└── Task 31: Create learnings storage + critical-patterns.md [unspecified-high]

Wave 5 (After Wave 4 — Optimization + Migration):
├── Task 32: Token budget optimization (session-start.py) [deep]
├── Task 33: Token budget optimization (prompt-enhancer.py) [deep]
├── Task 34: Add model-per-agent dispatch to runtime/team_router.py [unspecified-high]
├── Task 35: Update OAL-setup.sh migration for new features [unspecified-high]
├── Task 36: Update settings.json with all new hook registrations [quick]
└── Task 37: Update README.md with new features [writing]

Wave FINAL (After ALL — independent review, 4 parallel):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review + regression [unspecified-high]
├── Task F3: Full integration QA (all features end-to-end) [unspecified-high]
└── Task F4: Scope fidelity check [deep]

Critical Path: T1 → T8 → T18/T19 → T25/T26 → T32 → F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 7 (Waves 0 and 3)
```

### Token Budget Allocation (HARD CONSTRAINT from Metis G1)

```
Session-start total:   ≤ 2000 chars (≤ 200 chars when no features active)
├── Profile/project:     200 chars (always)
├── Working memory:      400 chars (if exists)
├── Handoff context:     300 chars (if <48h old)
├── Memory context:      300 chars (ON-DEMAND: only if memory files exist)
├── Active failures:     200 chars (ON-DEMAND: only if failure-tracker has entries)
├── Tools inventory:     100 chars
├── Planning state:      100 chars (ON-DEMAND: only if _plan.md or ralph-loop.json exists)
├── Ralph loop state:    100 chars (ON-DEMAND: only if ralph-loop.json exists)
└── Buffer:              300 chars

Prompt-enhancer total: ≤ 1000 chars
├── Intent + discipline:  200 chars (includes simplifier directives)
├── Knowledge retrieval:  300 chars (existing, top-2)
├── Compound learnings:   200 chars (ON-DEMAND: only if learnings exist)
├── Agent/model routing:  200 chars (ON-DEMAND: only if domain signals detected)
├── Mode injection:       100 chars (ON-DEMAND: only if ulw/crazy/mode signal)
└── Buffer:               000 chars
```

### Model-Per-Agent Routing Table (NEW)

```
Agent Definition          │ Preferred Model   │ Trigger Keywords
──────────────────────────┼───────────────────┼──────────────────────────────
frontend-designer         │ gemini-cli        │ ui, ux, css, layout, responsive, visual
backend-engineer          │ codex-cli         │ api, server, database, logic, algorithm
security-auditor          │ codex-cli         │ auth, encrypt, cors, jwt, vulnerability
database-engineer         │ codex-cli         │ sql, migration, schema, query, index
testing-engineer          │ claude (native)   │ test, spec, coverage, fixture, mock
infra-engineer            │ codex-cli         │ docker, ci/cd, deploy, terraform, k8s
research-mode (cognitive) │ claude (native)   │ research, find, how to, explain, docs
architect-mode (cognitive)│ claude (native)   │ architect, design, plan, structure
implement-mode (cognitive)│ domain-dependent  │ implement, build, create, add
```

### Stop Hook Priority Order (from Metis G2)

```
Priority 0: stop_hook_active guard → exit(0) immediately (INFINITE LOOP PREVENTION)
Priority 1: Ralph loop check → block if iteration < max
Priority 2: Planning enforcement → block if phase incomplete
Priority 3: Evidence gate (existing CHECK1-CHECK6)
Priority 4: Simplifier advisory (NEW CHECK 7 — stderr only, never blocks)
───────── SEPARATE EVENT: SessionEnd (NOT Stop) ─────────
Capture A: Memory capture → write .oal/state/memory/
Capture B: Compound learning → write .oal/knowledge/learnings/
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1-7 | — | 8-11, 12-17 | 0 |
| 8 | 1, 2, 3 | 18, 19, 21, 22, 25, 30 | 1 |
| 9 | 2, 3 | 19, 20, 26, 27, 30, 31 | 1 |
| 10 | 2 | — | 1 |
| 11 | 2 | 21, 22 | 1 |
| 12-16 | 1-7 | — | 2 |
| 17 | 1, 2, 3 | 33 | 2 |
| 18 | 8 | 25 | 3 |
| 19 | 8, 9 | 26, 27 | 3 |
| 20 | 9 | 27 | 3 |
| 21, 22 | 8, 11 | — | 3 |
| 23, 24 | 3, 4 | 28, 29, 34 | 3 |
| 25 | 18 | 32 | 4 |
| 26, 27 | 19, 20 | 32 | 4 |
| 28, 29 | 23, 24 | 33 | 4 |
| 30, 31 | 8, 9 | 33 | 4 |
| 32-37 | 25-31 | F1-F4 | 5 |
| F1-F4 | 32-37 | — | FINAL |

### Agent Dispatch Summary

| Wave | Tasks | Categories |
|------|-------|-----------|
| 0 | 7 | T1-T4,T7 → `quick`, T5 → `quick`, T6 → `unspecified-high` |
| 1 | 4 | T8 → `deep`, T9,T11 → `unspecified-high`, T10 → `quick` |
| 2 | 6 | T12,T13,T15,T17 → `unspecified-high`, T14,T16 → `quick` |
| 3 | 7 | T18,T19 → `deep`, T20-T23 → `unspecified-high`, T24 → `quick` |
| 4 | 7 | T25,T26 → `deep`, T27-T31 → `unspecified-high` |
| 5 | 6 | T32,T33 → `deep`, T34 → `unspecified-high`, T35,T36 → `quick`, T37 → `writing` |
| FINAL | 4 | F1 → `oracle`, F2-F3 → `unspecified-high`, F4 → `deep` |
---

## TODOs

> Implementation + Test = ONE Task. Never separate.
> EVERY task MUST have: Recommended Agent Profile + Parallelization info + QA Scenarios.

### Wave 0 — Foundation (Tasks 1-7)

- [x] 1. Fix `stop_hook_active` Bug in stop-gate.py

  **What to do**:
  - In `hooks/stop-gate.py`, add a guard at the VERY TOP (after JSON parse, before any checks) that reads `data.get("stop_hook_active")`. If `True`, immediately `sys.exit(0)` with no output.
  - The guard must be BEFORE all CHECK blocks (lines 147-369 currently).
  - Use `_common.py` import: `from _common import json_input` — but stop-gate currently parses JSON inline (line 23). Refactor to use `json_input()` for consistency.
  - Add unit test: `tests/test_stop_gate.py::test_stop_hook_active_guard`

  **Must NOT do**:
  - Do NOT restructure the existing CHECK 1-6 logic. Only ADD the guard.
  - Do NOT change the output format of existing block decisions.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`
  - `stop_hook_active` is a 5-line guard addition. Trivial change.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 2, 3, 4, 5, 6, 7)
  - **Blocks**: Tasks 8-11 (Stop Hook Multiplexer depends on this fix)
  - **Blocked By**: None

  **References**:
  - `hooks/stop-gate.py:22-26` — Current JSON parse (replace with `json_input()`)
  - `hooks/stop-gate.py:147-369` — All CHECK blocks (guard must precede these)
  - `hooks/_common.py:7-12` — `json_input()` function to use
  - `hooks/_common.py:31-33` — `block_decision()` helper (existing, for reference)
  - hooks-mastery plugin analysis: `stop_hook_active` boolean in Stop payload prevents infinite loops

  **Acceptance Criteria**:
  - [x] `echo '{"stop_hook_active":true}' | python3 hooks/stop-gate.py; echo $?` → exit 0, empty stdout
  - [x] `echo '{"stop_hook_active":false}' | python3 hooks/stop-gate.py; echo $?` → exit 0 (normal check flow)
  - [x] `python3 -m pytest tests/test_stop_gate.py::test_stop_hook_active_guard -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: stop_hook_active=true prevents blocking
    Tool: Bash
    Preconditions: hooks/stop-gate.py has the new guard
    Steps:
      1. echo '{"stop_hook_active":true}' | python3 hooks/stop-gate.py > /tmp/sg_out.json 2>/dev/null
      2. cat /tmp/sg_out.json | python3 -c "import sys; content=sys.stdin.read().strip(); assert content=='', f'Expected empty but got: {content}'"
      3. echo $?  # Must be 0
    Expected Result: Empty stdout, exit code 0 — no block decision emitted
    Failure Indicators: Non-empty stdout containing 'decision' or non-zero exit
    Evidence: .sisyphus/evidence/task-1-stop-hook-active-guard.txt

  Scenario: stop_hook_active=false allows normal flow
    Tool: Bash
    Preconditions: No source writes in ledger (clean state)
    Steps:
      1. echo '{"stop_hook_active":false}' | python3 hooks/stop-gate.py > /tmp/sg_normal.json 2>/dev/null
      2. echo $?  # Must be 0
    Expected Result: Exit 0, normal check flow executes (may or may not block depending on state)
    Evidence: .sisyphus/evidence/task-1-stop-hook-normal-flow.txt
  ```

  **Commit**: YES
  - Message: `fix(hooks): add stop_hook_active guard to prevent infinite loop in stop-gate.py`
  - Files: `hooks/stop-gate.py`, `tests/test_stop_gate.py`
  - Pre-commit: `python3 -m pytest tests/test_stop_gate.py -x -q`

- [x] 2. Add Hook Error Logging to _common.py

  **What to do**:
  - Add `log_hook_error(hook_name, error, context=None)` function to `hooks/_common.py`.
  - Logs to `.oal/state/ledger/hook-errors.jsonl` with fields: `{"ts": ISO8601, "hook": name, "error": str(error), "context": context}`.
  - Use atomic write: write to `.tmp` file, then `os.rename()`. For JSONL: open in append mode with file lock (`fcntl.flock`).
  - Rotation: if file > 100KB, rename to `.hook-errors.jsonl.1` and start fresh.
  - Update `setup_crash_handler()` to call `log_hook_error()` inside the `_excepthook` function.
  - Add `atomic_json_write(path, data)` utility for atomic state file writes (used by many future tasks).
  - Add unit test: `tests/test_common.py::test_log_hook_error` and `test_atomic_json_write`

  **Must NOT do**:
  - Do NOT add any external dependencies. Pure stdlib only.
  - Do NOT change the exit behavior of `setup_crash_handler` (must still exit 0).

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`
  - Utility function additions to shared module. Straightforward.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 1, 3, 4, 5, 6, 7)
  - **Blocks**: Tasks 8, 9, 10, 11 (all new hooks import from _common.py)
  - **Blocked By**: None

  **References**:
  - `hooks/_common.py:1-62` — Full file (all existing utilities)
  - `hooks/_common.py:36-50` — `setup_crash_handler()` (modify to log errors)
  - `hooks/_common.py:53-62` — `read_file_safe()` (pattern for safe file ops)
  - `hooks/tool-ledger.py` — Existing JSONL append pattern (reference for hook-errors.jsonl)

  **Acceptance Criteria**:
  - [x] `python3 -c "from _common import log_hook_error; log_hook_error('test','err')"` → creates `.oal/state/ledger/hook-errors.jsonl`
  - [x] `python3 -c "from _common import atomic_json_write; atomic_json_write('/tmp/test.json', {'a':1})"` → file exists with correct content
  - [x] `python3 -m pytest tests/test_common.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Error logging creates JSONL entry
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/ledger
      2. python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import log_hook_error; log_hook_error('test-hook','sample error',{'key':'val'})"
      3. tail -1 .oal/state/ledger/hook-errors.jsonl | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); assert d['hook']=='test-hook' and d['error']=='sample error'"
    Expected Result: Last line of JSONL has correct hook name and error message
    Evidence: .sisyphus/evidence/task-2-error-logging.txt

  Scenario: Crash handler logs before exit
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import setup_crash_handler; setup_crash_handler('crash-test'); raise ValueError('boom')" 2>/dev/null; echo $?
      2. Assert exit code is 0
      3. tail -1 .oal/state/ledger/hook-errors.jsonl | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); assert 'boom' in d['error']"
    Expected Result: Exit 0, error logged to JSONL
    Evidence: .sisyphus/evidence/task-2-crash-handler-logging.txt
  ```

  **Commit**: YES (groups with Task 3)
  - Message: `feat(hooks): add error logging and atomic write utilities to _common.py`
  - Files: `hooks/_common.py`, `tests/test_common.py`
  - Pre-commit: `python3 -m pytest tests/test_common.py -x -q`

- [x] 3. Add Feature Flags System to _common.py + settings.json

  **What to do**:
  - Add `get_feature_flag(flag_name, default=True)` to `hooks/_common.py`.
  - Resolution order: (1) env var `OAL_{FLAG_NAME}_ENABLED` → (2) `settings.json._oal.features.{flag_name}` → (3) default.
  - Add `_oal.features` section to `settings.json` with flags:
    ```json
    "features": {
      "memory": true,
      "ralph_loop": true,
      "planning_enforcement": true,
      "compound_learning": true,
      "simplifier": true,
      "model_routing": true,
      "agent_registry": true
    }
    ```
  - The function must cache the settings.json parse (read once per hook invocation, not per call).
  - Add unit test: `tests/test_common.py::test_feature_flags`

  **Must NOT do**:
  - Do NOT watch/poll the file. Read once, cache in module-level dict.
  - Do NOT fail if settings.json is missing or malformed — return default.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 1, 2, 4, 5, 6, 7)
  - **Blocks**: Tasks 8-11, 17-24 (all new features check their flag)
  - **Blocked By**: None

  **References**:
  - `hooks/_common.py:1-62` — Add function here
  - `settings.json:210-220` — Existing `_oal` section (add `features` sub-key)
  - `hooks/prompt-enhancer.py:42-45` — Existing `MAX_CHARS`/`budget_ok()` pattern (for reference on config access)

  **Acceptance Criteria**:
  - [x] `OAL_MEMORY_ENABLED=0 python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import get_feature_flag; assert not get_feature_flag('memory')"` → PASS
  - [x] `python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import get_feature_flag; assert get_feature_flag('memory')"` → PASS (default=True)
  - [x] `python3 -m pytest tests/test_common.py::test_feature_flags -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Feature flag from env var overrides settings
    Tool: Bash
    Steps:
      1. OAL_MEMORY_ENABLED=0 python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import get_feature_flag; print(get_feature_flag('memory'))"
      2. Assert output is 'False'
    Expected Result: Env var takes priority over settings.json
    Evidence: .sisyphus/evidence/task-3-feature-flags-env.txt

  Scenario: Missing settings.json returns default
    Tool: Bash
    Steps:
      1. CLAUDE_PROJECT_DIR=/tmp/nonexistent python3 -c "import sys; sys.path.insert(0,'hooks'); from _common import get_feature_flag; print(get_feature_flag('nonexistent_feature', default=True))"
      2. Assert output is 'True'
    Expected Result: Default value returned when settings.json not found
    Evidence: .sisyphus/evidence/task-3-feature-flags-default.txt
  ```

  **Commit**: YES (groups with Task 2)
  - Message: `feat(hooks): add feature flags system with env var + settings.json resolution`
  - Files: `hooks/_common.py`, `settings.json`, `tests/test_common.py`
  - Pre-commit: `python3 -m pytest tests/test_common.py -x -q`

- [x] 4. Create Token Budget Allocation Constants

  **What to do**:
  - Create `hooks/_budget.py` with named constants for every token budget allocation:
    ```python
    # Session-start budgets (chars)
    BUDGET_SESSION_TOTAL = 2000
    BUDGET_SESSION_IDLE = 200  # When no features active
    BUDGET_PROFILE = 200
    BUDGET_WORKING_MEMORY = 400
    BUDGET_HANDOFF = 300
    BUDGET_MEMORY = 300
    BUDGET_FAILURES = 200
    BUDGET_TOOLS = 100
    BUDGET_PLANNING = 100
    BUDGET_RALPH = 100
    # Prompt-enhancer budgets (chars)
    BUDGET_PROMPT_TOTAL = 1000
    BUDGET_INTENT_DISCIPLINE = 200  # includes simplifier
    BUDGET_KNOWLEDGE = 300
    BUDGET_LEARNINGS = 200
    BUDGET_AGENT_ROUTING = 200
    BUDGET_MODE = 100
    ```
  - Replace magic numbers in `session-start.py` (line 189: `1500`) and `prompt-enhancer.py` (line 42: `MAX_CHARS = 800`) with imports from `_budget.py`.
  - Add unit test: `tests/test_budget.py::test_budget_totals_consistent`

  **Must NOT do**:
  - Do NOT change any behavioral logic. Only replace magic numbers with named constants.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 1, 2, 3, 5, 6, 7)
  - **Blocks**: Tasks 23, 32, 33 (agent registry + token optimization use these constants)
  - **Blocked By**: None

  **References**:
  - `hooks/session-start.py:28` — `_read_file(path, max_bytes=2000)` and line 189 implicit 1500 char cap
  - `hooks/prompt-enhancer.py:42` — `MAX_CHARS = 800` (replace with BUDGET_PROMPT_TOTAL)
  - `settings.json:215-219` — `context_budget` section (keep in sync)

  **Acceptance Criteria**:
  - [x] `python3 -c "import sys; sys.path.insert(0,'hooks'); from _budget import BUDGET_SESSION_TOTAL, BUDGET_PROMPT_TOTAL; assert BUDGET_SESSION_TOTAL == 2000 and BUDGET_PROMPT_TOTAL == 1000"` → PASS
  - [x] `grep -c 'MAX_CHARS = 800' hooks/prompt-enhancer.py` → 0 (magic number removed)
  - [x] `python3 -m pytest tests/test_budget.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Budget constants importable and consistent
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'hooks'); from _budget import *; assert BUDGET_PROFILE + BUDGET_WORKING_MEMORY + BUDGET_HANDOFF + BUDGET_MEMORY + BUDGET_FAILURES + BUDGET_TOOLS + BUDGET_PLANNING + BUDGET_RALPH <= BUDGET_SESSION_TOTAL"
    Expected Result: Sum of sub-budgets does not exceed total
    Evidence: .sisyphus/evidence/task-4-budget-consistency.txt

  Scenario: prompt-enhancer uses budget constant
    Tool: Bash
    Steps:
      1. grep 'from _budget import' hooks/prompt-enhancer.py | wc -l
      2. Assert output >= 1
      3. grep 'MAX_CHARS = 800' hooks/prompt-enhancer.py | wc -l
      4. Assert output == 0
    Expected Result: Budget imported, magic number gone
    Evidence: .sisyphus/evidence/task-4-budget-import.txt
  ```

  **Commit**: YES
  - Message: `refactor(hooks): extract token budget constants to _budget.py`
  - Files: `hooks/_budget.py`, `hooks/session-start.py`, `hooks/prompt-enhancer.py`, `tests/test_budget.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`


- [x] 5. Set Up pytest Infrastructure

  **What to do**:
  - Create `tests/` directory with `conftest.py` and `__init__.py`.
  - `conftest.py` should: (1) add `hooks/` to `sys.path`, (2) create a temp project dir fixture (`tmp_project`), (3) set `CLAUDE_PROJECT_DIR` env var in fixture.
  - Create `tests/conftest.py` with fixtures: `tmp_project` (creates `.oal/state/ledger/`, `.oal/knowledge/`, etc.), `mock_stdin(data)` (patches sys.stdin with JSON), `clean_env` (clears OAL_ env vars).
  - Verify setup: `python3 -m pytest tests/ --collect-only` should discover test files.
  - Add `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` with `testpaths = ["tests"]`.

  **Must NOT do**:
  - Do NOT install any test dependencies beyond pytest (no pytest-cov, pytest-mock yet).

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`python-testing`]
  - `python-testing`: pytest infrastructure setup, fixtures, conftest patterns.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 1, 2, 3, 4, 6, 7)
  - **Blocks**: Tasks 6, 7 (test files need infrastructure), all later tasks (all include tests)
  - **Blocked By**: None

  **References**:
  - `hooks/_common.py` — Functions that tests will import
  - `hooks/state_migration.py` — `resolve_state_file`, `resolve_state_dir` used by all hooks

  **Acceptance Criteria**:
  - [x] `python3 -m pytest tests/ --collect-only 2>&1 | grep 'no tests ran\|collected 0'` → matches (infrastructure exists, no tests yet is OK)
  - [x] `test -f tests/conftest.py && test -f tests/__init__.py` → both exist

  **QA Scenarios:**
  ```
  Scenario: pytest discovers test directory
    Tool: Bash
    Steps:
      1. python3 -m pytest tests/ --collect-only 2>&1
      2. Assert exit code is 0 or 5 (5 = no tests collected, which is OK for infra-only)
    Expected Result: pytest recognizes the tests/ directory without errors
    Evidence: .sisyphus/evidence/task-5-pytest-collect.txt
  ```

  **Commit**: YES (groups with Tasks 6, 7)
  - Message: `feat(test): add pytest infrastructure with conftest fixtures`
  - Files: `tests/__init__.py`, `tests/conftest.py`, `pytest.ini`
  - Pre-commit: `python3 -m pytest tests/ --collect-only`

- [x] 6. Write Baseline Hook Tests

  **What to do**:
  - Write tests for ALL existing hooks to establish a regression baseline.
  - One test file per hook: `tests/test_stop_gate.py`, `tests/test_prompt_enhancer.py`, `tests/test_session_start.py`, `tests/test_circuit_breaker.py`.
  - Each file must test at least: (1) valid JSON input → expected output, (2) invalid JSON → exit 0, (3) missing state files → graceful degradation.
  - Test by subprocess: `subprocess.run(['python3', 'hooks/X.py'], input=json_bytes, capture_output=True)`. This matches how Claude Code invokes hooks.
  - For `prompt-enhancer.py`: test intent classification for each intent type (fix/plan/refactor/review/research/implement).
  - For `stop-gate.py`: test each CHECK (1-6) independently by crafting appropriate ledger/state.
  - For `circuit-breaker.py`: test failure tracking and pattern normalization.
  - For `session-start.py`: test profile injection, handoff detection.
  - Target: ≥20 tests total across all files.

  **Must NOT do**:
  - Do NOT modify any hook source code. Tests only.
  - Do NOT mock internal functions — test via subprocess to match real invocation.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]
  - Requires understanding of each hook's behavior from source. Non-trivial test design.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 1-5, 7)
  - **Blocks**: All later tasks (regression baseline)
  - **Blocked By**: Task 5 (pytest infra)

  **References**:
  - `hooks/stop-gate.py:1-369` — All CHECK blocks to test
  - `hooks/prompt-enhancer.py:58-89` — INTENT_MAP to test classification
  - `hooks/prompt-enhancer.py:125-131` — ULW/CRAZY signal detection
  - `hooks/circuit-breaker.py:30-57` — Failure detection + pattern normalization
  - `hooks/session-start.py:39-50` — Profile parsing logic

  **Acceptance Criteria**:
  - [x] `python3 -m pytest tests/ -x -q` → ≥20 tests pass, 0 failures
  - [x] `python3 -m pytest tests/ -x -q --tb=short 2>&1 | tail -1` → shows `N passed`

  **QA Scenarios:**
  ```
  Scenario: Baseline tests all pass
    Tool: Bash
    Steps:
      1. python3 -m pytest tests/ -x -q 2>&1
      2. Assert exit code is 0
      3. Assert output contains 'passed' and not 'failed'
    Expected Result: All baseline tests pass, establishing regression safety net
    Evidence: .sisyphus/evidence/task-6-baseline-tests.txt

  Scenario: Invalid input causes graceful exit
    Tool: Bash
    Steps:
      1. echo 'NOT_JSON' | python3 hooks/stop-gate.py; echo $?
      2. Assert exit code is 0
      3. echo 'NOT_JSON' | python3 hooks/prompt-enhancer.py; echo $?
      4. Assert exit code is 0
    Expected Result: All hooks exit 0 on invalid input (crash isolation)
    Evidence: .sisyphus/evidence/task-6-invalid-input.txt
  ```

  **Commit**: YES (groups with Tasks 5, 7)
  - Message: `test(hooks): add baseline regression tests for all existing hooks`
  - Files: `tests/test_stop_gate.py`, `tests/test_prompt_enhancer.py`, `tests/test_session_start.py`, `tests/test_circuit_breaker.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 7. Create Shared Test Helpers

  **What to do**:
  - Create `tests/helpers.py` with reusable test utilities:
    ```python
    def run_hook(hook_name, input_data, env=None, cwd=None) -> (stdout, stderr, exit_code):
        """Run a hook via subprocess, return (stdout_json, stderr, exit_code)."""
    def make_ledger_entry(tool, command=None, exit_code=0, file=None, success=True) -> dict:
        """Create a tool-ledger.jsonl entry for testing."""
    def setup_state(tmp_dir, files_dict) -> None:
        """Create state files from a dict of {relative_path: content}."""
    def assert_injection_contains(output, *keywords):
        """Assert contextInjection contains all keywords."""
    def assert_injection_under_budget(output, max_chars):
        """Assert contextInjection length is within budget."""
    ```
  - These helpers will be used by ALL subsequent test files.

  **Must NOT do**:
  - Do NOT add external dependencies.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 1-6)
  - **Blocks**: All tasks that write tests
  - **Blocked By**: Task 5 (pytest infra)

  **References**:
  - `tests/conftest.py` — Fixtures (created in Task 5)
  - `hooks/_common.py` — Pattern reference for utility design

  **Acceptance Criteria**:
  - [x] `python3 -c "from tests.helpers import run_hook, make_ledger_entry, setup_state"` → no ImportError
  - [x] `python3 -m pytest tests/ -x -q` → still passes (helpers don't break anything)

  **QA Scenarios:**
  ```
  Scenario: Test helpers importable and functional
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'.'); from tests.helpers import run_hook; out,err,rc = run_hook('stop-gate', {'stop_hook_active':True}); assert rc==0"
    Expected Result: run_hook helper successfully invokes stop-gate.py
    Evidence: .sisyphus/evidence/task-7-test-helpers.txt
  ```

  **Commit**: YES (groups with Tasks 5, 6)
  - Message: `test(helpers): add shared test utilities for hook testing`
  - Files: `tests/helpers.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

### Wave 1 — Stop Hook Multiplexer (Tasks 8-11)

- [x] 8. Refactor stop-gate.py → stop_dispatcher.py

  **What to do**:
  - Create `hooks/stop_dispatcher.py` that replaces `stop-gate.py` as the Stop hook entry point.
  - Architecture: Priority-based dispatcher that runs checks in defined order:
    ```
    P0: stop_hook_active guard → exit(0)
    P1: Ralph loop check → block if active + iteration < max
    P2: Planning enforcement → block if phase incomplete
    P3: Evidence gate (existing CHECK 1-6, extracted from stop-gate.py)
    P4: Simplifier advisory (CHECK 7 — stderr only)
    ```
  - Extract CHECK 1-6 from `stop-gate.py` into functions: `check_verification()`, `check_evidence_pack()`, `check_diff_budget()`, `check_recent_failures()`, `check_test_execution()`, `check_false_fix()`, `check_write_failures()`.
  - Each check returns `(blocks: list[str], advisories: list[str])`.
  - P1 and P2 are stubs initially (just `pass`) — implemented in Tasks 18 and 22.
  - Import `get_feature_flag` from `_common.py` — skip any check whose flag is disabled.
  - Keep `stop-gate.py` as a thin wrapper that imports and calls `stop_dispatcher.main()` for backward compatibility.
  - Update tests to cover the dispatcher flow.

  **Must NOT do**:
  - Do NOT change the behavior of existing CHECK 1-6. Extract, don't rewrite.
  - Do NOT implement Ralph (P1) or Planning (P2) logic yet — stubs only.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-testing`]
  - Complex refactoring: extracting 300+ lines into modular functions while preserving behavior.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 9, 10, 11)
  - **Blocks**: Tasks 18, 19, 21, 22, 25, 30 (all features that plug into dispatcher)
  - **Blocked By**: Tasks 1, 2, 3 (need guard fix, logging, feature flags)

  **References**:
  - `hooks/stop-gate.py:1-369` — FULL FILE — All logic to extract into modular functions
  - `hooks/stop-gate.py:22-26` — JSON parse (use `json_input()` instead)
  - `hooks/stop-gate.py:93-99` — `shadow_manager` import (keep optional)
  - `hooks/stop-gate.py:147-193` — CHECK 1 + CHECK 1b (evidence)
  - `hooks/stop-gate.py:225-267` — CHECK 2 (diff budget)
  - `hooks/stop-gate.py:269-283` — CHECK 3 (recent failures)
  - `hooks/stop-gate.py:285-301` — CHECK 4 (test files modified)
  - `hooks/stop-gate.py:303-327` — CHECK 5 (false fix)
  - `hooks/stop-gate.py:329-356` — CHECK 6 (write failures)
  - `hooks/stop-gate.py:358-369` — OUTPUT (block decision format)
  - `hooks/_common.py:31-33` — `block_decision()` helper
  - Ralph Wiggum plugin: dispatcher priority chain pattern
  - hooks-mastery plugin: exit code protocol (`exit(2)` = block in PreToolUse)

  **Acceptance Criteria**:
  - [x] `echo '{"stop_hook_active":true}' | python3 hooks/stop_dispatcher.py; echo $?` → exit 0, no output
  - [x] `echo '{}' | python3 hooks/stop-gate.py` → same behavior as before refactor (wrapper works)
  - [x] `python3 -m pytest tests/test_stop_dispatcher.py -x -q` → ≥8 tests pass
  - [x] `python3 -c "from stop_dispatcher import check_verification, check_diff_budget, check_false_fix"` → all importable

  **QA Scenarios:**
  ```
  Scenario: Dispatcher preserves existing CHECK behavior
    Tool: Bash
    Preconditions: Create a temp project with source writes in ledger but no test runs
    Steps:
      1. Set up temp project: mkdir -p /tmp/test-proj/.oal/state/ledger
      2. Create ledger entry with Write tool but no test commands
      3. CLAUDE_PROJECT_DIR=/tmp/test-proj echo '{"stop_hook_active":false}' | python3 hooks/stop_dispatcher.py
      4. Assert output contains 'decision' and 'block'
    Expected Result: CHECK 1 (no verification) triggers block, same as old stop-gate.py
    Evidence: .sisyphus/evidence/task-8-dispatcher-check1.txt

  Scenario: Dispatcher P0 short-circuits all checks
    Tool: Bash
    Steps:
      1. echo '{"stop_hook_active":true}' | python3 hooks/stop_dispatcher.py > /tmp/p0_out.txt 2>/dev/null
      2. test ! -s /tmp/p0_out.txt  # File should be empty
    Expected Result: P0 guard exits immediately, no checks run
    Evidence: .sisyphus/evidence/task-8-dispatcher-p0.txt
  ```

  **Commit**: YES
  - Message: `refactor(hooks): extract stop-gate checks into stop_dispatcher.py multiplexer`
  - Files: `hooks/stop_dispatcher.py`, `hooks/stop-gate.py` (thin wrapper), `tests/test_stop_dispatcher.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 9. Create SessionEnd Capture Hook Skeleton

  **What to do**:
  - Create `hooks/session-end-capture.py` for the `SessionEnd` event.
  - This hook fires AFTER the session ends (fire-and-forget, no blocking capability).
  - Skeleton structure:
    ```python
    #!/usr/bin/env python3
    """SessionEnd Hook — Captures memory + learnings after session completes."""
    from _common import setup_crash_handler, json_input, get_feature_flag, log_hook_error
    setup_crash_handler('session-end-capture', fail_closed=False)
    data = json_input()
    # Capture A: Memory (implemented in Task 19)
    if get_feature_flag('memory'):
        pass  # stub
    # Capture B: Compound learning (implemented in Task 30)
    if get_feature_flag('compound_learning'):
        pass  # stub
    ```
  - Register in `~/.claude/settings.json` hooks array (document the registration, don't auto-modify user settings).
  - Add test: `tests/test_session_end_capture.py`

  **Must NOT do**:
  - Do NOT implement actual capture logic yet. Stubs only.
  - Do NOT auto-modify `~/.claude/settings.json` — document the manual step.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 8, 10, 11)
  - **Blocks**: Tasks 19, 20, 26, 27, 30, 31 (memory + learning plug into this)
  - **Blocked By**: Tasks 2, 3 (logging, feature flags)

  **References**:
  - `hooks/session-start.py:1-20` — Hook boilerplate pattern (imports, crash handler, json_input)
  - Metis finding #3: Use SessionEnd for capture (fire-and-forget, no timeout risk)
  - Metis finding #8: SessionEnd is one of 6 unused hook events
  - hooks-mastery plugin: SessionEnd event schema `{session_id, cwd, duration_ms}`

  **Acceptance Criteria**:
  - [x] `echo '{"session_id":"test"}' | python3 hooks/session-end-capture.py; echo $?` → exit 0
  - [x] `python3 -m pytest tests/test_session_end_capture.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: SessionEnd hook exits cleanly with stubs
    Tool: Bash
    Steps:
      1. echo '{"session_id":"s1","cwd":"/tmp"}' | python3 hooks/session-end-capture.py 2>/dev/null; echo $?
      2. Assert exit code is 0
    Expected Result: Hook runs without errors despite stub implementations
    Evidence: .sisyphus/evidence/task-9-session-end-skeleton.txt
  ```

  **Commit**: YES (groups with Tasks 10, 11)
  - Message: `feat(hooks): add SessionEnd capture hook skeleton`
  - Files: `hooks/session-end-capture.py`, `tests/test_session_end_capture.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 10. Add PostToolUseFailure Hook for Enhanced Failure Tracking

  **What to do**:
  - Create `hooks/post-tool-failure.py` for the `PostToolUseFailure` event.
  - This event fires when a tool call fails (different from PostToolUse which fires on success too).
  - Log failure to `.oal/state/ledger/hook-errors.jsonl` with: tool name, error, timestamp.
  - Increment failure counter in `failure-tracker.json` (similar to circuit-breaker.py but for ALL tool types).
  - Feature flag: `get_feature_flag('failure_tracking')`.

  **Must NOT do**:
  - Do NOT duplicate circuit-breaker.py logic. This is for hook-level failures, not tool-level.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 8, 9, 11)
  - **Blocks**: None (standalone enhancement)
  - **Blocked By**: Task 2 (logging utility)

  **References**:
  - `hooks/circuit-breaker.py:1-60` — Failure tracking pattern (reference, don't duplicate)
  - Metis finding #8: PostToolUseFailure is one of 6 unused hook events

  **Acceptance Criteria**:
  - [x] `echo '{"tool_name":"Bash","error":"timeout"}' | python3 hooks/post-tool-failure.py; echo $?` → exit 0
  - [x] After above: `tail -1 .oal/state/ledger/hook-errors.jsonl` contains 'timeout'

  **QA Scenarios:**
  ```
  Scenario: Tool failure gets logged
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/ledger
      2. echo '{"tool_name":"Write","error":"permission denied"}' | python3 hooks/post-tool-failure.py
      3. tail -1 .oal/state/ledger/hook-errors.jsonl | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); assert d['error']=='permission denied'"
    Expected Result: Failure logged with correct tool name and error
    Evidence: .sisyphus/evidence/task-10-tool-failure-logging.txt
  ```

  **Commit**: YES (groups with Tasks 9, 11)
  - Message: `feat(hooks): add PostToolUseFailure hook for enhanced failure tracking`
  - Files: `hooks/post-tool-failure.py`, `tests/test_post_tool_failure.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 11. Create PreToolUse Plan Injection Hook

  **What to do**:
  - Create `hooks/pre-tool-inject.py` for the `PreToolUse` event.
  - When `_plan.md` or `_checklist.md` exists, inject a context reminder before each tool call:
    ```python
    plan_path = resolve_state_file(project_dir, 'state/_plan.md', '_plan.md')
    if os.path.exists(plan_path) and get_feature_flag('planning_enforcement'):
        with open(plan_path) as f:
            head = ''.join(f.readlines()[:15])  # First 15 lines
        # Emit as contextInjection (NOT deny/allow)
        json.dump({'contextInjection': f'@plan-reminder: {head[:200]}'}, sys.stdout)
    ```
  - Inspired by planning-with-files: `cat task_plan.md | head -30` on every tool call.
  - OAL version is lighter: only first 15 lines, only 200 chars, only when _plan.md exists.
  - Feature flag: `get_feature_flag('planning_enforcement')`.

  **Must NOT do**:
  - Do NOT block or deny tool calls. Only inject context.
  - Do NOT read the full plan file (performance: max 15 lines).

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 8, 9, 10)
  - **Blocks**: Tasks 21, 22 (planning features build on this)
  - **Blocked By**: Task 2 (logging utility)

  **References**:
  - planning-with-files plugin: `head -30 task_plan.md` forced re-read pattern
  - `hooks/prompt-enhancer.py:318-331` — Existing checklist reading (similar but per-prompt, not per-tool)
  - hooks-mastery plugin: PreToolUse event schema

  **Acceptance Criteria**:
  - [x] With `_plan.md` present: `echo '{"tool_name":"Write"}' | python3 hooks/pre-tool-inject.py` → output contains `@plan-reminder`
  - [x] Without `_plan.md`: `echo '{"tool_name":"Write"}' | python3 hooks/pre-tool-inject.py; echo $?` → exit 0, no output

  **QA Scenarios:**
  ```
  Scenario: Plan reminder injected when _plan.md exists
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state && echo '# My Plan\n## Phase 1\n- Fix auth' > .oal/state/_plan.md
      2. echo '{"tool_name":"Write"}' | python3 hooks/pre-tool-inject.py
      3. Assert output contains 'plan-reminder' and 'Fix auth'
    Expected Result: First 15 lines of plan injected as context
    Evidence: .sisyphus/evidence/task-11-plan-inject.txt

  Scenario: No injection when _plan.md absent
    Tool: Bash
    Steps:
      1. rm -f .oal/state/_plan.md
      2. echo '{"tool_name":"Write"}' | python3 hooks/pre-tool-inject.py > /tmp/no_plan.txt 2>/dev/null
      3. test ! -s /tmp/no_plan.txt
    Expected Result: Empty output, clean exit
    Evidence: .sisyphus/evidence/task-11-no-plan.txt
  ```

  **Commit**: YES (groups with Tasks 9, 10)
  - Message: `feat(hooks): add PreToolUse plan injection hook for forced re-read`
  - Files: `hooks/pre-tool-inject.py`, `tests/test_pre_tool_inject.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

### Wave 2 — Bug Fixes + Quality (Tasks 12-17)

- [x] 12. Fix Command Routing Bugs (OAL:crazy, OAL:deep-plan)

  **What to do**:
  - **OAL:crazy** (`commands/OAL:crazy.md`): Fix the routing that sends to wrong agents. Ensure Claude=orchestrator, Codex=deep-code+security, Gemini=UI/UX is enforced in the command template.
  - **OAL:deep-plan** (`commands/OAL:deep-plan.md`): Fix intent understanding — currently jumps to execution instead of asking clarifying questions first.
  - Audit all 19 command files for: broken command references, outdated routing instructions, missing intent classification.
  - Fix any commands referencing deprecated paths (`.omc/` instead of `.oal/`).

  **Must NOT do**:
  - Do NOT add new commands. Fix existing only.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 13-17)
  - **Blocks**: None (bug fixes don't block new features)
  - **Blocked By**: Tasks 1-7 (foundation must be in place)

  **References**:
  - `commands/OAL:crazy.md:1-91` — Crazy mode command (fix routing)
  - `commands/OAL:deep-plan.md:1-142` — Deep plan command (fix intent flow)
  - `commands/` directory — All 19 command files for audit
  - `hooks/prompt-enhancer.py:130-131` — CRAZY_SIGNALS detection

  **Acceptance Criteria**:
  - [x] `grep -c '.omc/' commands/*.md` → 0 (no deprecated paths)
  - [x] `grep -l 'Codex=deep-code' commands/OAL:crazy.md` → matches

  **QA Scenarios:**
  ```
  Scenario: OAL:crazy command has correct routing
    Tool: Bash
    Steps:
      1. grep -i 'codex' commands/OAL\:crazy.md | head -3
      2. Assert contains 'deep-code' or 'security' or 'backend'
      3. grep -i 'gemini' commands/OAL\:crazy.md | head -3
      4. Assert contains 'UI' or 'UX' or 'frontend' or 'visual'
    Expected Result: Command file has clear Codex=backend, Gemini=frontend routing
    Evidence: .sisyphus/evidence/task-12-command-routing.txt
  ```

  **Commit**: YES
  - Message: `fix(commands): fix routing bugs in OAL:crazy and OAL:deep-plan`
  - Files: `commands/OAL:crazy.md`, `commands/OAL:deep-plan.md`, other affected commands
  - Pre-commit: `grep -rc '.omc/' commands/ | grep -v ':0$' | wc -l` (must be 0)

- [x] 13. Fix prompt-enhancer Stuck Detection + Dedup

  **What to do**:
  - `hooks/prompt-enhancer.py:429-445`: stuck detection currently reads failure-tracker but doesn't dedup.
  - If the same stuck signal fires 3 times in a row, it injects the same `@stuck` message repeatedly.
  - Fix: Track last stuck injection in a session-level state file (`.oal/state/.last-stuck-ts`).
  - If last stuck injection was <60 seconds ago, skip re-injection (dedup).
  - Also fix: stuck signals should check failure count threshold, not just keyword match.

  **Must NOT do**:
  - Do NOT change the stuck signal keywords.
  - Do NOT change the escalation message format.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 12, 14-17)
  - **Blocks**: None
  - **Blocked By**: Tasks 1-7

  **References**:
  - `hooks/prompt-enhancer.py:429-445` — Current stuck detection code
  - `hooks/circuit-breaker.py:42-57` — Pattern normalization (reference for dedup)

  **Acceptance Criteria**:
  - [x] Two rapid stuck signals produce only ONE injection (dedup works)
  - [x] `python3 -m pytest tests/test_prompt_enhancer.py::test_stuck_dedup -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Stuck dedup prevents repeated injection
    Tool: Bash
    Steps:
      1. echo '{"tool_input":{"user_message":"stuck same error"}}' | python3 hooks/prompt-enhancer.py > /tmp/stuck1.json
      2. sleep 0.1
      3. echo '{"tool_input":{"user_message":"stuck same error"}}' | python3 hooks/prompt-enhancer.py > /tmp/stuck2.json
      4. Compare: second should NOT contain @stuck if within dedup window
    Expected Result: Dedup prevents redundant injection
    Evidence: .sisyphus/evidence/task-13-stuck-dedup.txt
  ```

  **Commit**: YES (groups with Task 14)
  - Message: `fix(hooks): add dedup to prompt-enhancer stuck detection`
  - Files: `hooks/prompt-enhancer.py`, `tests/test_prompt_enhancer.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 14. Fix circuit-breaker Pattern Normalization

  **What to do**:
  - `hooks/circuit-breaker.py:42-57`: Pattern normalization is incomplete.
  - `npm test` and `npm run test` should be same pattern. Currently only strips `run`/`exec` but misses:
    - `npx jest` vs `jest` (same thing)
    - `python -m pytest` vs `pytest` (same thing)
    - `bun test` vs `bunx vitest` (different but related)
  - Add normalization for: `python3 -m X` → `X`, `npx X` → `X`.
  - On success, clear ALL similar pattern variants (not just exact match).

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Tasks 1-7

  **References**:
  - `hooks/circuit-breaker.py:42-57` — Current normalization code
  - `hooks/circuit-breaker.py:59-end` — Tracker load/save logic

  **Acceptance Criteria**:
  - [x] `npm test` and `npm run test` produce same pattern key
  - [x] Success on `npm test` clears `npm run test` entry too

  **QA Scenarios:**
  ```
  Scenario: npm test and npm run test are same pattern
    Tool: Bash
    Steps:
      1. Create two failure entries with 'npm test' and 'npm run test'
      2. Check failure-tracker.json has one pattern, not two
    Expected Result: Both commands map to same pattern key
    Evidence: .sisyphus/evidence/task-14-pattern-normalization.txt
  ```

  **Commit**: YES (groups with Task 13)
  - Message: `fix(hooks): improve circuit-breaker pattern normalization`
  - Files: `hooks/circuit-breaker.py`, `tests/test_circuit_breaker.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 15. Fix CCG/Teams Python CLI Integration

  **What to do**:
  - `runtime/team_router.py` and `scripts/oal.py`: CCG/Teams commands shell out to Python CLI.
  - Known issues: path resolution fails when OAL is not in `~/.claude/`, subprocess timeout not set.
  - Fix: Use `os.path.dirname(__file__)` for reliable path resolution.
  - Add 30-second timeout to all subprocess calls.
  - Test with actual `codex-cli` and `gemini-cli` availability detection.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Tasks 1-7

  **References**:
  - `runtime/team_router.py` — Team routing logic
  - `scripts/oal.py` — CLI entrypoint
  - `commands/OAL:ccg.md` — CCG command template
  - `commands/OAL:teams.md` — Teams command template

  **Acceptance Criteria**:
  - [x] `python3 scripts/oal.py compat list 2>&1` → exit 0 (no path errors)
  - [x] All subprocess calls in `runtime/team_router.py` have `timeout=` parameter

  **QA Scenarios:**
  ```
  Scenario: CLI entrypoint resolves paths correctly
    Tool: Bash
    Steps:
      1. python3 scripts/oal.py compat list 2>&1; echo $?
      2. Assert exit code is 0
    Expected Result: No ImportError or path resolution failures
    Evidence: .sisyphus/evidence/task-15-cli-paths.txt
  ```

  **Commit**: YES
  - Message: `fix(runtime): fix CCG/Teams path resolution and add subprocess timeouts`
  - Files: `runtime/team_router.py`, `scripts/oal.py`
  - Pre-commit: `python3 scripts/oal.py compat list`

- [x] 16. Fix Knowledge Retrieval .index.json Corruption

  **What to do**:
  - `hooks/prompt-enhancer.py:359-408`: The `.index.json` cache can become corrupted if:
    - Two hooks write simultaneously (race condition)
    - JSON is partially written (crash during write)
  - Fix: Use `atomic_json_write()` from Task 2 for index writes.
  - Add try/except around index load that deletes corrupted index and rebuilds.
  - Add max index entries cap (100 files) to prevent unbounded growth.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Tasks 1-7 (specifically Task 2 for atomic_json_write)

  **References**:
  - `hooks/prompt-enhancer.py:359-408` — Index build/save code
  - `hooks/_common.py` — `atomic_json_write()` (from Task 2)

  **Acceptance Criteria**:
  - [x] Corrupted `.index.json` is auto-repaired on next prompt
  - [x] `grep 'atomic_json_write' hooks/prompt-enhancer.py` → matches

  **QA Scenarios:**
  ```
  Scenario: Corrupted index auto-repairs
    Tool: Bash
    Steps:
      1. echo 'CORRUPTED{{{' > .oal/knowledge/.index.json
      2. echo '{"tool_input":{"user_message":"implement auth feature"}}' | python3 hooks/prompt-enhancer.py
      3. python3 -c "import json; json.load(open('.oal/knowledge/.index.json'))" 2>&1; echo $?
      4. Assert exit code is 0 (valid JSON now)
    Expected Result: Corrupted index deleted, rebuilt with valid JSON
    Evidence: .sisyphus/evidence/task-16-index-repair.txt
  ```

  **Commit**: YES
  - Message: `fix(hooks): use atomic writes for .index.json and add corruption recovery`
  - Files: `hooks/prompt-enhancer.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 17. Implement Code Simplifier (Anti-AI-Slop)

  **What to do**:
  - **PREVENTIVE (prompt-enhancer.py)**: Enhance the existing `@discipline` injection (line 105-112) to include anti-slop directives. Replace:
    ```python
    # OLD:
    "@discipline: Senior engineer mode. Ship production code. VERIFY every change..."
    # NEW:
    "@discipline: Senior engineer mode. Ship production code. "
    "VERIFY every change (run it). NEVER claim done without evidence. "
    "Write CLEAN minimal code: NO noise comments (// get user, // return result), "
    "NO over-abstraction, NO generic names (data/result/item/temp/val/obj). "
    "Comments ONLY for non-obvious business logic. Prefer simple inline over extracted."
    ```
  - **DETECTIVE (stop_dispatcher.py)**: Add CHECK 7 — Simplifier Advisory. After CHECK 6, scan `source_write_entries` for:
    1. **Comment ratio**: Read each written file, count comment lines vs total. If >40% → advisory.
    2. **Generic names**: Regex `\b(data|result|item|temp|val|obj|info|stuff|thing)\b` in `def/let/const/var` lines.
    3. **Noise comments**: Regex `^\s*(#|//) (get|set|return|check|create|update|delete|increment) ` — comment restates code.
    4. **Commented-out code**: Lines matching `^\s*(#|//) .*[{(;=]` (code-like content in comments).
  - CHECK 7 is ADVISORY ONLY — write to `advisories` list (stderr), NEVER to `blocks` list.
  - Feature flag: `get_feature_flag('simplifier')`.
  - Add tests: `tests/test_simplifier.py`

  **Must NOT do**:
  - Do NOT make CHECK 7 blocking. It is ALWAYS advisory (stderr warning).
  - Do NOT scan files >10KB (performance: skip large files).
  - Do NOT change the output format of existing block decisions.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]
  - Requires regex patterns for slop detection + understanding of prompt-enhancer injection system.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 12-16)
  - **Blocks**: Task 33 (token optimization includes simplifier budget)
  - **Blocked By**: Tasks 1, 2, 3 (guard fix, logging, feature flags)

  **References**:
  - `hooks/prompt-enhancer.py:105-117` — Existing `@discipline` injection (MODIFY this)
  - `hooks/stop-gate.py:329-356` — CHECK 6 pattern (reference for CHECK 7 structure)
  - `hooks/stop-gate.py:31-42` — NON_SOURCE_PATTERNS (reuse for filtering)
  - `hooks/stop_dispatcher.py` — (from Task 8) where CHECK 7 will be added
  - Superpowers plugin: anti-rationalization tables (inspiration for slop detection)

  **Acceptance Criteria**:
  - [x] `echo '{"tool_input":{"user_message":"implement auth"}}' | python3 hooks/prompt-enhancer.py | grep -i 'noise comment\|clean\|minimal'` → matches
  - [x] CHECK 7 detects slop in a test file with >40% comments → advisory in stderr
  - [x] CHECK 7 does NOT block completion (no 'decision' in stdout for slop)
  - [x] `python3 -m pytest tests/test_simplifier.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Discipline injection includes anti-slop
    Tool: Bash
    Steps:
      1. echo '{"tool_input":{"user_message":"implement new feature"}}' | python3 hooks/prompt-enhancer.py > /tmp/simplify_out.json
      2. python3 -c "import json; d=json.load(open('/tmp/simplify_out.json')); ci=d.get('contextInjection',''); assert 'noise comment' in ci.lower() or 'generic name' in ci.lower() or 'clean' in ci.lower(), f'Missing simplifier in: {ci[:200]}'"
    Expected Result: @discipline injection contains anti-slop directives
    Evidence: .sisyphus/evidence/task-17-simplifier-preventive.txt

  Scenario: CHECK 7 detects high comment ratio (advisory only)
    Tool: Bash
    Steps:
      1. Create a test Python file with 60% comments:
         echo -e '# Comment 1\n# Comment 2\n# Comment 3\nprint("hello")\n# Comment 4\n# Comment 5' > /tmp/sloppy.py
      2. Create ledger entry for writing that file
      3. Run stop_dispatcher with the file in source_write_entries
      4. Assert stderr contains 'comment ratio' or 'simplifier'
      5. Assert stdout does NOT contain 'decision' (not blocking)
    Expected Result: Advisory warning in stderr, no blocking in stdout
    Evidence: .sisyphus/evidence/task-17-simplifier-detective.txt

  Scenario: Clean code passes CHECK 7 silently
    Tool: Bash
    Steps:
      1. Create a clean Python file with <10% comments
      2. Run stop_dispatcher with the file in source_write_entries
      3. Assert stderr does NOT contain simplifier warnings
    Expected Result: No advisory for clean code
    Evidence: .sisyphus/evidence/task-17-simplifier-clean.txt
  ```

  **Commit**: YES
  - Message: `feat(hooks): add code simplifier — anti-AI-slop in discipline injection + CHECK 7 advisory`
  - Files: `hooks/prompt-enhancer.py`, `hooks/stop_dispatcher.py`, `tests/test_simplifier.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

### Wave 3 — Core Features (Tasks 18-24)

- [x] 18. Implement Ralph True Loop (State File + Block Logic)

  **What to do**:
  - Create Ralph loop state file format: `.oal/state/ralph-loop.json`
    ```json
    {"active": true, "iteration": 3, "max_iterations": 50,
     "original_prompt": "fix all tests", "started_at": "ISO8601",
     "checklist_path": ".oal/state/_checklist.md"}
    ```
  - In `hooks/stop_dispatcher.py` (from Task 8), implement P1 (Ralph loop check):
    ```python
    def check_ralph_loop(project_dir, data):
        ralph_path = os.path.join(project_dir, '.oal/state/ralph-loop.json')
        if not os.path.exists(ralph_path): return [], []
        state = json.load(open(ralph_path))
        if not state.get('active'): return [], []
        iteration = state.get('iteration', 0)
        max_iter = state.get('max_iterations', 50)
        if iteration >= max_iter:
            state['active'] = False
            atomic_json_write(ralph_path, state)
            return [], ['Ralph loop reached max iterations. Stopping.']
        # Block completion — re-inject original prompt
        state['iteration'] = iteration + 1
        atomic_json_write(ralph_path, state)
        return [f"Ralph loop iteration {iteration+1}/{max_iter}. Continue: {state.get('original_prompt','')}"], []
    ```
  - Activation: `/OAL:ralph-start` command or `ralph` keyword in prompt-enhancer creates the state file.
  - Deactivation: max iterations reached OR `rm .oal/state/ralph-loop.json` OR `/OAL:ralph-stop`.
  - The block decision uses `{"decision":"block","reason":"<original_prompt_with_progress>"}` to re-inject work.
  - **Claude Code protocol**: Stop hook stdout `{"decision":"block","reason":"..."}` — exactly per spec.

  **Must NOT do**:
  - Do NOT implement checklist parsing here (that's Task 22).
  - Do NOT call any external API. Pure file-based state.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-testing`]
  - Complex state machine with race condition concerns + hook protocol compliance.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 19-24)
  - **Blocks**: Task 25 (Ralph injection + escape hatch)
  - **Blocked By**: Task 8 (stop_dispatcher.py)

  **References**:
  - `hooks/stop_dispatcher.py` — (from Task 8) P1 stub to implement
  - `hooks/_common.py` — `atomic_json_write()`, `get_feature_flag('ralph_loop')`
  - Ralph Wiggum plugin: `{"decision":"block","reason":"<prompt>"}` pattern
  - Ralph Wiggum plugin: state file `.claude/ralph-loop.local.md` with YAML frontmatter + iteration counter
  - `rules/contextual/persistent-mode.md` — Current ULW/Ralph rule (keyword-only, to be enhanced)

  **Acceptance Criteria**:
  - [x] Ralph loop blocks completion when active: `echo '{"stop_hook_active":false}' | python3 hooks/stop_dispatcher.py` → stdout contains `"decision":"block"`
  - [x] Ralph increments iteration counter on each block
  - [x] Ralph stops at max_iterations (default 50)
  - [x] `python3 -m pytest tests/test_ralph.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Ralph blocks and re-injects prompt
    Tool: Bash
    Steps:
      1. echo '{"active":true,"iteration":0,"max_iterations":50,"original_prompt":"fix all tests"}' > .oal/state/ralph-loop.json
      2. echo '{"stop_hook_active":false}' | python3 hooks/stop_dispatcher.py > /tmp/ralph_out.json
      3. python3 -c "import json; d=json.load(open('/tmp/ralph_out.json')); assert d['decision']=='block'; assert 'fix all tests' in d['reason']"
      4. python3 -c "import json; s=json.load(open('.oal/state/ralph-loop.json')); assert s['iteration']==1"
    Expected Result: Completion blocked, iteration incremented, original prompt in reason
    Evidence: .sisyphus/evidence/task-18-ralph-block.txt

  Scenario: Ralph stops at max iterations
    Tool: Bash
    Steps:
      1. echo '{"active":true,"iteration":50,"max_iterations":50,"original_prompt":"test"}' > .oal/state/ralph-loop.json
      2. echo '{"stop_hook_active":false}' | python3 hooks/stop_dispatcher.py > /tmp/ralph_max.json
      3. cat /tmp/ralph_max.json  # Should NOT contain 'block'
      4. python3 -c "import json; s=json.load(open('.oal/state/ralph-loop.json')); assert not s['active']"
    Expected Result: Ralph deactivates, does not block
    Evidence: .sisyphus/evidence/task-18-ralph-max.txt
  ```

  **Commit**: YES
  - Message: `feat(ralph): implement true Ralph loop with Stop hook blocking and state management`
  - Files: `hooks/stop_dispatcher.py`, `.oal/state/ralph-loop.json` (template), `tests/test_ralph.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 19. Implement Memory Capture on SessionEnd

  **What to do**:
  - In `hooks/session-end-capture.py` (from Task 9), implement Capture A (memory).
  - On SessionEnd, summarize the session by reading:
    1. `.oal/state/ledger/tool-ledger.jsonl` — last 50 entries (what tools were used)
    2. `.oal/state/working-memory.md` — current working state
    3. `.oal/state/_checklist.md` — progress (if exists)
  - Write summary to `.oal/state/memory/{date}-{session_id_short}.md`:
    ```markdown
    # Session: 2026-02-28 (ses_abc)
    ## What Was Done
    - [tool summaries from ledger: files written, commands run]
    ## Key Decisions
    - [extracted from working-memory if available]
    ## Outcome
    - Checklist: 5/8 complete
    ```
  - NO AI synthesis. Pure extraction and formatting from existing files.
  - Max output: 500 chars per memory file.
  - Feature flag: `get_feature_flag('memory')`.

  **Must NOT do**:
  - Do NOT call any LLM API. Text extraction only.
  - Do NOT read files >5KB (performance).

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 18, 20-24)
  - **Blocks**: Tasks 26, 27 (memory retrieval + session-start integration)
  - **Blocked By**: Tasks 8, 9 (dispatcher + SessionEnd skeleton)

  **References**:
  - `hooks/session-end-capture.py` — (from Task 9) Stub to implement
  - `hooks/tool-ledger.py` — Ledger format reference (JSONL entries)
  - memsearch plugin: plain .md storage, `context: fork` retrieval pattern
  - `hooks/_common.py` — `atomic_json_write()`, `read_file_safe()`

  **Acceptance Criteria**:
  - [x] After SessionEnd: `.oal/state/memory/` contains a new .md file
  - [x] Memory file is ≤500 chars
  - [x] `python3 -m pytest tests/test_memory_capture.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Memory captured on SessionEnd
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/ledger .oal/state/memory
      2. echo '{"ts":"2026-02-28T10:00:00Z","tool":"Write","file":"src/auth.ts"}' > .oal/state/ledger/tool-ledger.jsonl
      3. echo '{"session_id":"ses_test","cwd":"'$(pwd)'"}' | python3 hooks/session-end-capture.py
      4. ls .oal/state/memory/*.md | wc -l
      5. Assert count >= 1
    Expected Result: Memory file created with session summary
    Evidence: .sisyphus/evidence/task-19-memory-capture.txt
  ```

  **Commit**: YES
  - Message: `feat(memory): implement session memory capture on SessionEnd`
  - Files: `hooks/session-end-capture.py`, `tests/test_memory_capture.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 20. Implement Memory Storage Format + Rotation

  **What to do**:
  - Memory files live in `.oal/state/memory/` as plain .md files.
  - Naming: `{YYYY-MM-DD}-{session_id_short}.md` (e.g., `2026-02-28-ses_abc.md`).
  - Rotation: if >50 files in directory, delete oldest until 50 remain.
  - Dedup: if file with same date+session already exists, append instead of overwrite.
  - Add `_memory.py` utility module in `hooks/` with:
    ```python
    def get_recent_memories(project_dir, max_files=5, max_chars_total=300):
        """Read most recent memory files, return concatenated summary."""
    def rotate_memories(project_dir, max_files=50):
        """Delete oldest memory files if count exceeds max."""
    ```

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 18, 19, 21-24)
  - **Blocks**: Task 27 (memory integration into session-start)
  - **Blocked By**: Task 9 (SessionEnd skeleton)

  **References**:
  - memsearch plugin: plain .md file storage pattern
  - `hooks/_common.py` — `read_file_safe()` utility pattern

  **Acceptance Criteria**:
  - [x] 55 memory files → after rotation only 50 remain (oldest 5 deleted)
  - [x] `get_recent_memories()` returns ≤300 chars from last 5 files
  - [x] `python3 -m pytest tests/test_memory_storage.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Memory rotation keeps max 50 files
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/memory
      2. for i in $(seq 1 55); do echo "memory $i" > .oal/state/memory/2026-01-$(printf '%02d' $i)-test.md; done
      3. python3 -c "import sys; sys.path.insert(0,'hooks'); from _memory import rotate_memories; rotate_memories('.')"
      4. ls .oal/state/memory/*.md | wc -l
      5. Assert count == 50
    Expected Result: Oldest 5 files deleted, 50 remain
    Evidence: .sisyphus/evidence/task-20-memory-rotation.txt
  ```

  **Commit**: YES (groups with Task 19)
  - Message: `feat(memory): add memory storage format, rotation, and retrieval utilities`
  - Files: `hooks/_memory.py`, `tests/test_memory_storage.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 21. Implement Planning Enforcement (Forced Re-Read)

  **What to do**:
  - In `hooks/pre-tool-inject.py` (from Task 11), enhance the plan injection:
    - Read first 15 lines of `_plan.md` AND current checklist progress.
    - Inject as `@plan-reminder: Phase 2/4 | 3/8 done | Next: implement auth middleware`.
    - Only inject for Write/Edit/Bash tools (skip Read, Glob, Grep — read operations don't need plan reminders).
  - Add planning-aware context to prompt-enhancer when `_plan.md` exists.
  - Inspired by planning-with-files: forced re-read on every tool call.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 18-20, 22-24)
  - **Blocks**: None (standalone enhancement)
  - **Blocked By**: Tasks 8, 11 (dispatcher + PreToolUse hook)

  **References**:
  - `hooks/pre-tool-inject.py` — (from Task 11) Enhance with checklist awareness
  - planning-with-files plugin: `head -30 task_plan.md` pattern
  - `hooks/prompt-enhancer.py:318-331` — Existing checklist reading

  **Acceptance Criteria**:
  - [x] Write tool call with active plan → `@plan-reminder` in output
  - [x] Read tool call with active plan → NO injection (skip read tools)

  **QA Scenarios:**
  ```
  Scenario: Plan reminder injected for Write but not Read
    Tool: Bash
    Steps:
      1. echo '# Plan\n## Phase 1\n- [x] Fix auth' > .oal/state/_plan.md
      2. echo '{"tool_name":"Write"}' | python3 hooks/pre-tool-inject.py > /tmp/plan_write.json
      3. Assert output contains '@plan-reminder'
      4. echo '{"tool_name":"Read"}' | python3 hooks/pre-tool-inject.py > /tmp/plan_read.json
      5. Assert output is empty or does not contain '@plan-reminder'
    Expected Result: Plan injected for mutation tools only
    Evidence: .sisyphus/evidence/task-21-planning-enforcement.txt
  ```

  **Commit**: YES (groups with Task 22)
  - Message: `feat(planning): add forced plan re-read on mutation tool calls`
  - Files: `hooks/pre-tool-inject.py`, `tests/test_pre_tool_inject.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 22. Implement Planning Completion Gate

  **What to do**:
  - In `hooks/stop_dispatcher.py`, implement P2 (Planning enforcement):
    ```python
    def check_planning_gate(project_dir):
        checklist = resolve_state_file(project_dir, 'state/_checklist.md', '_checklist.md')
        if not os.path.exists(checklist): return [], []
        with open(checklist) as f:
            lines = f.readlines()
        total = sum(1 for l in lines if l.strip().startswith(('[ ]','[x]','[!]','-  [ ]','- [x]')))
        done = sum(1 for l in lines if '[x]' in l.lower())
        blocked = sum(1 for l in lines if '[!]' in l)
        pending = total - done - blocked
        if pending > 0:
            return [f'Planning gate: {done}/{total} complete, {pending} pending. Complete checklist before finishing.'], []
        return [], []
    ```
  - If checklist exists and has pending items → block completion.
  - `[!]` marks are treated as 'blocked/skipped' (not counted as pending).
  - **Scope drift detection (CHECK 8)**: Compare `git diff --name-only` against files mentioned in `_plan.md`. If >30% are outside plan, add advisory.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 18-21, 23-24)
  - **Blocks**: None
  - **Blocked By**: Tasks 8, 11 (dispatcher + PreToolUse hook)

  **References**:
  - `hooks/stop_dispatcher.py` — (from Task 8) P2 stub to implement
  - planning-with-files plugin: `grep -c '**Status:** complete'` phase counting
  - `hooks/stop-gate.py:225-267` — Existing diff budget check (pattern for scope drift)

  **Acceptance Criteria**:
  - [x] Checklist with pending items → blocks completion
  - [x] Checklist all [x] → allows completion
  - [x] Scope drift detected and reported as advisory

  **QA Scenarios:**
  ```
  Scenario: Incomplete checklist blocks completion
    Tool: Bash
    Steps:
      1. echo '- [x] Done task\n- [x] Pending task' > .oal/state/_checklist.md
      2. echo '{"stop_hook_active":false}' | python3 hooks/stop_dispatcher.py > /tmp/plan_gate.json
      3. python3 -c "import json; d=json.load(open('/tmp/plan_gate.json')); assert d['decision']=='block'; assert 'pending' in d['reason'].lower()"
    Expected Result: Completion blocked with 'N pending' message
    Evidence: .sisyphus/evidence/task-22-planning-gate.txt

  Scenario: Complete checklist allows completion
    Tool: Bash
    Steps:
      1. echo '- [x] Done 1\n- [x] Done 2' > .oal/state/_checklist.md
      2. echo '{"stop_hook_active":false}' | python3 hooks/stop_dispatcher.py > /tmp/plan_ok.json
      3. cat /tmp/plan_ok.json  # Should not contain planning gate block
    Expected Result: No planning gate block when all items done
    Evidence: .sisyphus/evidence/task-22-planning-pass.txt
  ```

  **Commit**: YES (groups with Task 21)
  - Message: `feat(planning): add checklist completion gate and scope drift detection`
  - Files: `hooks/stop_dispatcher.py`, `tests/test_planning_gate.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 23. Create Agent Registry with Model Routing + MCP Awareness

  **What to do**:
  - Create `hooks/_agent_registry.py` — the central agent dispatch table:
    ```python
    AGENT_REGISTRY = {
        'frontend-designer': {
            'preferred_model': 'gemini-cli',
            'task_category': 'visual-engineering',
            'skills': ['frontend-design', 'frontend-ui-ux'],
            'trigger_keywords': ['ui', 'ux', 'css', 'layout', 'responsive', 'visual', 'frontend', 'component'],
            'mcp_tools': ['puppeteer_screenshot', 'puppeteer_navigate'],  # MCP tools this agent should prefer
            'description': 'Frontend/UI specialist. Uses Gemini for visual tasks.',
        },
        'backend-engineer': {
            'preferred_model': 'codex-cli',
            'task_category': 'deep',
            'skills': ['backend-patterns', 'api-design'],
            'trigger_keywords': ['api', 'server', 'database', 'logic', 'algorithm', 'backend', 'endpoint'],
            'mcp_tools': [],
            'description': 'Backend/logic specialist. Uses Codex for deep reasoning.',
        },
        'security-auditor': {
            'preferred_model': 'codex-cli',
            'task_category': 'deep',
            'skills': ['security-review'],
            'trigger_keywords': ['auth', 'encrypt', 'cors', 'jwt', 'vulnerability', 'security', 'xss', 'csrf'],
            'mcp_tools': ['sentry_search_issues', 'sentry_get_issue_details'],
            'description': 'Security specialist. Uses Codex for deep security analysis.',
        },
        'database-engineer': {
            'preferred_model': 'codex-cli',
            'task_category': 'unspecified-high',
            'skills': [],
            'trigger_keywords': ['sql', 'migration', 'schema', 'query', 'index', 'database', 'postgres', 'mongo'],
            'mcp_tools': [],
            'description': 'Database specialist. Schema design, query optimization, migrations.',
        },
        'testing-engineer': {
            'preferred_model': 'claude',  # native
            'task_category': 'unspecified-high',
            'skills': ['python-testing', 'e2e-testing'],
            'trigger_keywords': ['test', 'spec', 'coverage', 'fixture', 'mock', 'playwright', 'e2e'],
            'mcp_tools': ['puppeteer_navigate', 'puppeteer_screenshot'],
            'description': 'Testing specialist. Unit tests, integration tests, E2E with Playwright.',
        },
        'infra-engineer': {
            'preferred_model': 'codex-cli',
            'task_category': 'unspecified-high',
            'skills': ['docker-patterns'],
            'trigger_keywords': ['docker', 'ci', 'cd', 'deploy', 'terraform', 'k8s', 'kubernetes', 'nginx'],
            'mcp_tools': [],
            'description': 'Infrastructure specialist. Docker, CI/CD, deployment, cloud.',
        },
        # Cognitive modes
        'research-mode': {
            'preferred_model': 'claude',
            'task_category': None,  # uses subagent_type instead
            'subagent_type': 'librarian',
            'skills': [],
            'trigger_keywords': ['research', 'find', 'how to', 'explain', 'documentation'],
            'mcp_tools': ['web_search_exa', 'google_search', 'context7_query-docs'],
            'description': 'Research mode. Web search, docs lookup, library exploration.',
        },
        'architect-mode': {
            'preferred_model': 'claude',
            'task_category': None,
            'subagent_type': 'oracle',
            'skills': [],
            'trigger_keywords': ['architect', 'design', 'plan', 'structure', 'system'],
            'mcp_tools': [],
            'description': 'Architecture mode. System design, trade-off analysis.',
        },
        'implement-mode': {
            'preferred_model': 'domain-dependent',  # resolved at dispatch time
            'task_category': 'deep',
            'skills': [],
            'trigger_keywords': ['implement', 'build', 'create', 'add', 'develop'],
            'mcp_tools': [],
            'description': 'Implementation mode. Model chosen based on domain of task.',
        },
    }

    def resolve_agent(prompt_keywords: set[str]) -> dict | None:
        """Match prompt keywords to best agent. Returns registry entry or None."""

    def get_dispatch_params(agent_name: str) -> dict:
        """Get task() parameters for dispatching this agent."""

    def detect_available_models() -> dict:
        """Check which CLIs are available: codex-cli, gemini-cli."""
        # subprocess.run(['which', 'codex'], ...)

    def discover_mcp_tools() -> list[str]:
        """Read MCP config to find available tool names."""
        # Check ~/.claude/settings.json for mcpServers
    ```
  - **MCP discovery**: Read `~/.claude/settings.json` → `mcpServers` keys. Store as available tools.
  - **Model detection**: `which codex 2>/dev/null`, `which gemini 2>/dev/null`. Cache result per session.
  - **Claude Code protocol compliance**: All `task_category` values match Claude Code's valid categories.
  - **Fallback**: If `codex-cli` not available, fall back to `claude` (native). Never hard-fail.

  **Must NOT do**:
  - Do NOT auto-install CLIs. Only detect availability.
  - Do NOT read MCP server credentials or API keys.
  - Do NOT make network calls. Detection is local only.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 18-22, 24)
  - **Blocks**: Tasks 28, 29, 34 (routing + dispatch use registry)
  - **Blocked By**: Tasks 3, 4 (feature flags, budget constants)

  **References**:
  - `hooks/prompt-enhancer.py:209-261` — Current specialist routing (REPLACE with registry lookup)
  - `settings.json:210-220` — `_oal` config section
  - OMC team_router: model dispatch pattern
  - oh-my-opencode: `task()` dispatch with category + skills
  - everything-claude-code: cost-aware-llm-pipeline skill for model routing
  - Protocol Reference (above): task() parameters, CLI detection

  **Acceptance Criteria**:
  - [x] `python3 -c "from _agent_registry import resolve_agent; r=resolve_agent({'auth','login'}); assert r and r['preferred_model']=='codex-cli'"` → PASS
  - [x] `python3 -c "from _agent_registry import detect_available_models; m=detect_available_models(); assert 'claude' in m"` → PASS
  - [x] `python3 -m pytest tests/test_agent_registry.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Agent resolution for security keywords
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import resolve_agent; r=resolve_agent({'auth','jwt','vulnerability'}); print(r['preferred_model'], r['task_category'])"
      2. Assert output contains 'codex-cli' and 'deep'
    Expected Result: Security keywords resolve to security-auditor with codex-cli
    Evidence: .sisyphus/evidence/task-23-agent-resolve-security.txt

  Scenario: Agent resolution for UI keywords
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import resolve_agent; r=resolve_agent({'css','layout','responsive'}); print(r['preferred_model'])"
      2. Assert output contains 'gemini-cli'
    Expected Result: UI keywords resolve to frontend-designer with gemini-cli
    Evidence: .sisyphus/evidence/task-23-agent-resolve-ui.txt

  Scenario: Model detection with fallback
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'hooks'); from _agent_registry import detect_available_models; m=detect_available_models(); print(m); assert 'claude' in m"
    Expected Result: At minimum, 'claude' is always available as fallback
    Evidence: .sisyphus/evidence/task-23-model-detection.txt
  ```

  **Commit**: YES
  - Message: `feat(agents): create agent registry with model routing, MCP awareness, and CLI detection`
  - Files: `hooks/_agent_registry.py`, `tests/test_agent_registry.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 24. Create Domain Agent Definitions + Cognitive Agent Definitions

  **What to do**:
  - Create 9 agent .md files in `agents/` directory (6 domain + 3 cognitive):
    ```
    agents/oal-frontend-designer.md
    agents/oal-backend-engineer.md
    agents/oal-security-auditor.md
    agents/oal-database-engineer.md
    agents/oal-testing-engineer.md
    agents/oal-infra-engineer.md
    agents/oal-research-mode.md
    agents/oal-architect-mode.md
    agents/oal-implement-mode.md
    ```
  - Each agent .md follows Claude Code agent format with YAML frontmatter:
    ```markdown
    ---
    name: oal-frontend-designer
    preferred_model: gemini-cli
    ---
    # Frontend Designer Agent
    You are a specialist frontend developer focused on UI/UX, styling, responsive design, and visual quality.
    
    ## Preferred Tools
    - Playwright (puppeteer_navigate, puppeteer_screenshot) for visual verification
    - Write/Edit for CSS, HTML, JSX/TSX files
    - Bash for build/lint verification
    
    ## MCP Tools Available
    - puppeteer_* for browser automation and visual QA
    - context7 for framework documentation lookup
    
    ## Constraints
    - Focus on frontend files only. Do NOT modify backend/API code.
    - Always verify visual changes with a screenshot.
    - Use Gemini CLI for complex visual reasoning when available.
    ```
  - Each agent must specify:
    1. `preferred_model` in frontmatter (from Model-Per-Agent Routing Table)
    2. `## Preferred Tools` — which Claude Code tools this agent should prioritize
    3. `## MCP Tools Available` — which MCP tools are relevant
    4. `## Constraints` — what this agent must NOT do (scope boundaries)
    5. `## Guardrails` — domain-specific safety checks
  - **Strong guardrails per agent**:
    - `security-auditor`: MUST run `/OAL:security-review` before completing. MUST NOT approve code with hardcoded secrets.
    - `database-engineer`: MUST verify migrations are reversible. MUST NOT run destructive SQL without explicit confirmation.
    - `infra-engineer`: MUST use `--dry-run` for infrastructure changes. MUST NOT modify production configs directly.
    - `testing-engineer`: MUST achieve >0% new test coverage. MUST NOT mark tests as passing without running them.

  **Must NOT do**:
  - Do NOT create more than 9 new agent files (14 total with existing 5).
  - Do NOT remove or modify existing 5 agents (executor, architect, critic, qa-tester, escalation-router).

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`
  - Agent definitions are .md files with template content. No code logic.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 18-23)
  - **Blocks**: Tasks 28, 29 (cognitive modes + agent routing reference these)
  - **Blocked By**: Tasks 3, 4 (feature flags, budget constants)

  **References**:
  - `agents/oal-executor.md` — Existing agent format (follow this pattern)
  - `agents/oal-architect.md` — Existing agent format
  - Model-Per-Agent Routing Table (in Execution Strategy section)
  - Protocol Reference: Agent .md format

  **Acceptance Criteria**:
  - [x] `ls agents/oal-*.md | wc -l` → 14 (5 existing + 9 new)
  - [x] `grep -l 'preferred_model:' agents/oal-*.md | wc -l` → ≥9 (all new agents)
  - [x] Each agent has ## Preferred Tools, ## MCP Tools, ## Constraints sections

  **QA Scenarios:**
  ```
  Scenario: All agent files are valid markdown with frontmatter
    Tool: Bash
    Steps:
      1. for f in agents/oal-*.md; do head -1 "$f" | grep -q '^---$' || echo "FAIL: $f missing frontmatter"; done
      2. Assert no FAIL lines
    Expected Result: All agents have YAML frontmatter
    Evidence: .sisyphus/evidence/task-24-agent-frontmatter.txt

  Scenario: Security-auditor has mandatory guardrails
    Tool: Bash
    Steps:
      1. grep -i 'security-review' agents/oal-security-auditor.md | wc -l
      2. Assert count >= 1
      3. grep -i 'hardcoded secret' agents/oal-security-auditor.md | wc -l
      4. Assert count >= 1
    Expected Result: Security agent has explicit guardrails for review and secret detection
    Evidence: .sisyphus/evidence/task-24-security-guardrails.txt
  ```

  **Commit**: YES
  - Message: `feat(agents): add 9 domain + cognitive agent definitions with model routing and guardrails`
  - Files: `agents/oal-frontend-designer.md`, `agents/oal-backend-engineer.md`, (7 more)
  - Pre-commit: `ls agents/oal-*.md | wc -l` (must be 14)

### Wave 4 — Integration + Polish (Tasks 25-31)

- [x] 25. Ralph Prompt Re-Injection + Escape Hatch

  **What to do**:
  - In `hooks/stop_dispatcher.py`, enhance the P1 Ralph block (from Task 18) to produce a RICH re-injection prompt:
    ```python
    def format_ralph_block_reason(state, project_dir):
        """Build the reason string that Claude sees as its next prompt."""
        original = state.get('original_prompt', '')
        iteration = state.get('iteration', 0)
        max_iter = state.get('max_iterations', 50)
        checklist_path = state.get('checklist_path', '')
        
        # Read checklist progress if available
        progress = ''
        if checklist_path:
            full = os.path.join(project_dir, checklist_path)
            if os.path.exists(full):
                lines = open(full).readlines()
                done = sum(1 for l in lines if '[x]' in l.lower())
                total = sum(1 for l in lines if l.strip().startswith(('[ ]','[x]','[!]','-  [ ]','- [x]')))
                progress = f' | Progress: {done}/{total}'
        
        return (
            f"Ralph loop iteration {iteration}/{max_iter}{progress}. "
            f"Continue working on: {original}\n"
            f"If truly done, run: /OAL:ralph-stop"
        )
    ```
  - The `reason` field in `{"decision":"block","reason":"..."}` becomes the next user-facing prompt. Claude sees this as instructions to continue.
  - **Escape hatch**: Create `/OAL:ralph-stop` command (commands/OAL:ralph-stop.md) — deletes `.oal/state/ralph-loop.json`, confirms "Ralph loop stopped after N iterations."
  - Also create `/OAL:ralph-start` command (commands/OAL:ralph-start.md) — asks for goal, creates state file with active=true, iteration=0, max_iterations=50.
  - Add `ralph_loop` feature flag check in prompt-enhancer (existing `ulw`/`ralph` keyword detection at line ~278-296) to auto-create the state file when keywords detected.

  **Must NOT do**:
  - Do NOT parse or execute checklist items here (Task 22 handles planning gate).
  - Do NOT add any AI synthesis to the re-injection prompt. Pure template string.
  - Do NOT modify the Stop hook protocol — `{"decision":"block","reason":"..."}` is the only format.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]
    - `python-testing`: Hook logic with file I/O and JSON protocol needs test coverage.
  - **Skills Evaluated but Omitted**:
    - `backend-patterns`: This is hook scripting, not API/server work.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 26-31)
  - **Blocks**: None (Ralph is self-contained after this)
  - **Blocked By**: Task 18 (Ralph base implementation)

  **References**:

  **Pattern References**:
  - `hooks/stop_dispatcher.py` — (from Task 18) `check_ralph_loop()` function to enhance with `format_ralph_block_reason()`
  - `hooks/prompt-enhancer.py:278-296` — Current `ulw`/`ralph` keyword detection (enhance to also create state file)
  - `rules/contextual/persistent-mode.md` — Current ULW/Ralph rule text

  **API/Type References**:
  - Claude Code Stop hook protocol: `{"decision":"block","reason":"<string>"}` — reason becomes next prompt
  - `.oal/state/ralph-loop.json` schema (from Task 18)

  **External References**:
  - Ralph Wiggum plugin: `stop-hook.js` — block+reason pattern with iteration counter
  - planning-with-files: forced re-read concept (checklist progress in re-injection)

  **WHY Each Reference Matters**:
  - `stop_dispatcher.py` P1 handler: This is WHERE the re-injection logic lives.
  - `prompt-enhancer.py` keyword detection: Must also CREATE the state file when keywords detected.
  - Ralph Wiggum plugin: Proves the block+reason pattern works for autonomous loops.

  **Acceptance Criteria**:
  - [x] Ralph block reason includes checklist progress: reason contains `Progress: 3/8`
  - [x] `/OAL:ralph-stop` command file exists at `commands/OAL:ralph-stop.md`
  - [x] `/OAL:ralph-start` command file exists at `commands/OAL:ralph-start.md`
  - [x] Keyword `ralph` or `ulw` in prompt-enhancer auto-creates state file
  - [x] `python3 -m pytest tests/test_ralph.py -x` → PASS (extend from Task 18)

  **QA Scenarios:**
  ```
  Scenario: Ralph re-injection includes checklist progress
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state
      2. echo '- [x] Done 1\n- [x] Done 2\n- [x] Pending 3\n- [x] Pending 4' > .oal/state/_checklist.md
      3. Create ralph-loop.json with active=true, iteration=2, max_iterations=50, checklist_path set
      4. echo '{"stop_hook_active":false}' | python3 hooks/stop_dispatcher.py > /tmp/ralph_inject.json
      5. Assert reason contains 'Progress: 2/4' and 'fix all bugs'
    Expected Result: Block reason contains both progress (2/4) and original prompt
    Failure Indicators: Missing 'Progress' string, or original_prompt not in reason
    Evidence: .sisyphus/evidence/task-25-ralph-injection.txt

  Scenario: Keyword detection auto-creates Ralph state file
    Tool: Bash
    Steps:
      1. rm -f .oal/state/ralph-loop.json
      2. echo '{"tool_input":{"user_message":"ulw fix all the failing tests"}}' | python3 hooks/prompt-enhancer.py > /dev/null
      3. test -f .oal/state/ralph-loop.json && echo 'CREATED' || echo 'MISSING'
      4. Assert state file has active=true and original_prompt contains 'fix all the failing tests'
    Expected Result: State file auto-created with active=true and extracted prompt
    Failure Indicators: File not created, or original_prompt missing the extracted goal
    Evidence: .sisyphus/evidence/task-25-ralph-keyword-create.txt
  ```

  **Commit**: YES
  - Message: `feat(ralph): add rich prompt re-injection with progress, escape hatch commands, and keyword activation`
  - Files: `hooks/stop_dispatcher.py`, `hooks/prompt-enhancer.py`, `commands/OAL:ralph-stop.md`, `commands/OAL:ralph-start.md`, `tests/test_ralph.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 26. Memory Retrieval via context:fork Pattern

  **What to do**:
  - Extend `hooks/_memory.py` (from Task 20) with `search_memories()` function:
    ```python
    def search_memories(project_dir, query_keywords: list[str], max_results=3, max_chars=200) -> str:
        """Search memory files for relevant context via keyword match. Returns formatted summary."""
        memory_dir = os.path.join(project_dir, '.oal/state/memory')
        if not os.path.isdir(memory_dir): return ''
        results = []
        for fname in sorted(os.listdir(memory_dir), reverse=True):  # newest first
            if not fname.endswith('.md'): continue
            content = read_file_safe(os.path.join(memory_dir, fname), max_bytes=2048)
            score = sum(1 for kw in query_keywords if kw.lower() in content.lower())
            if score > 0: results.append((score, fname, content))
        results.sort(key=lambda x: -x[0])
        # Format top results within char budget
        summary_parts, chars_used = [], 0
        for score, fname, content in results[:max_results]:
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
            excerpt = ' '.join(lines[:3])[:100]
            if chars_used + len(excerpt) > max_chars: break
            summary_parts.append(f'[{fname}] {excerpt}')
            chars_used += len(excerpt)
        return '\n'.join(summary_parts)
    ```
  - The **context:fork pattern** (from memsearch): memory search runs in an ISOLATED context. Only the curated summary enters the main conversation. This prevents memory files from polluting working context.
  - In `hooks/prompt-enhancer.py`, add memory retrieval as lightweight injection (after keyword extraction ~line 344-380):
    ```python
    from _memory import search_memories
    if get_feature_flag('memory'):
        mem_context = search_memories(project_dir, keywords, max_results=3, max_chars=200)
        if mem_context:
            injections.append(f'@memory: {mem_context}')
    ```
  - **Budget**: Memory injection capped at 200 chars. Combined with other injections, must stay ≤1000 chars total.
  - Feature flag: `get_feature_flag('memory')` — disabled by default in v1.

  **Must NOT do**:
  - Do NOT use vector databases or embeddings. Keyword match only.
  - Do NOT read memory files >2KB each. Skip large files.
  - Do NOT inject memory if no keywords match. Zero-overhead when not relevant.
  - Do NOT exceed 200 chars for memory injection.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 25, 27-31)
  - **Blocks**: Task 27 (memory integration into session-start)
  - **Blocked By**: Tasks 19, 20 (memory capture + storage utilities)

  **References**:

  **Pattern References**:
  - `hooks/_memory.py` — (from Task 20) `get_recent_memories()`, `rotate_memories()` — extend with `search_memories()`
  - `hooks/prompt-enhancer.py:344-424` — Existing knowledge retrieval pattern (follow same injection style)
  - `hooks/_common.py` — `read_file_safe()` utility

  **External References**:
  - memsearch plugin: `context: fork` pattern — search in isolated context, only summary enters main
  - memsearch plugin: plain .md storage, ~60 tokens overhead

  **WHY Each Reference Matters**:
  - `_memory.py`: Executor extends this file (don't create new). Already has `get_recent_memories()` and `rotate_memories()`.
  - `prompt-enhancer.py:344-424`: Exact location where knowledge injections happen. Memory injection follows same `injections.append()` pattern.
  - memsearch's `context:fork`: Proves keyword-only search with plain .md files is sufficient.

  **Acceptance Criteria**:
  - [x] `search_memories()` returns relevant results for matching keywords
  - [x] `search_memories()` returns empty string when no keywords match
  - [x] Memory injection ≤200 chars in prompt-enhancer output
  - [x] `python3 -m pytest tests/test_memory_retrieval.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Memory search finds relevant past sessions
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/memory
      2. Create auth-related memory file: 2026-02-27-ses_abc.md with JWT/middleware content
      3. Create UI-related memory file: 2026-02-26-ses_def.md with CSS/grid content
      4. python3 -c "from _memory import search_memories; r=search_memories('.', ['jwt','auth']); assert 'JWT' in r or 'auth' in r; assert len(r) <= 200"
    Expected Result: Returns auth-related memory within 200 char budget
    Failure Indicators: Returns UI memory, exceeds 200 chars, or returns empty
    Evidence: .sisyphus/evidence/task-26-memory-search.txt

  Scenario: No memory match returns empty string
    Tool: Bash
    Steps:
      1. python3 -c "from _memory import search_memories; r=search_memories('.', ['zzz_nonexistent']); assert r == ''"
    Expected Result: Empty string for non-matching keywords
    Evidence: .sisyphus/evidence/task-26-memory-nomatch.txt
  ```

  **Commit**: YES (groups with Task 27)
  - Message: `feat(memory): add keyword-based memory search with context:fork pattern`
  - Files: `hooks/_memory.py`, `hooks/prompt-enhancer.py`, `tests/test_memory_retrieval.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 27. Memory Integration into session-start.py (On-Demand)

  **What to do**:
  - In `hooks/session-start.py`, add CONDITIONAL memory injection (around line 140-180):
    ```python
    from _memory import get_recent_memories
    if get_feature_flag('memory'):
        recent = get_recent_memories(project_dir, max_files=3, max_chars_total=150)
        if recent:
            context_parts.append(f'@recent-memory: {recent}')
    ```
  - **On-demand principle**: If `.oal/state/memory/` doesn't exist or is empty → ZERO overhead.
  - **Budget**: Recent memory capped at 150 chars within session-start's 2000 char budget.
  - **Dedup**: session-start injects RECENT (last 3 sessions). prompt-enhancer injects RELEVANT (keyword-matched). Different purposes.

  **Must NOT do**:
  - Do NOT create `.oal/state/memory/` directory. Only read if exists.
  - Do NOT inject if feature flag `memory` is disabled.
  - Do NOT exceed 150 chars for memory in session-start.
  - Do NOT duplicate prompt-enhancer's keyword search. This is time-based, not topic-based.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 25, 26, 28-31)
  - **Blocks**: None
  - **Blocked By**: Tasks 19, 20, 26 (memory capture, storage, search)

  **References**:
  - `hooks/session-start.py:140-180` — Existing context injection (handoff, working-memory). Follow same `context_parts.append()` pattern.
  - `hooks/_memory.py` — (from Tasks 20, 26) `get_recent_memories()` function
  - `hooks/_common.py` — `get_feature_flag('memory')` check pattern

  **Acceptance Criteria**:
  - [x] With memory files + feature enabled: output contains `@recent-memory:`
  - [x] Without memory files: output does NOT contain `@recent-memory:`
  - [x] With feature disabled: output does NOT contain `@recent-memory:`
  - [x] session-start total output ≤2000 chars

  **QA Scenarios:**
  ```
  Scenario: Session-start injects recent memory when available
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/memory
      2. Create memory file: 2026-02-27-ses_test.md with "Fixed auth bug" content
      3. echo '{}' | python3 hooks/session-start.py > /tmp/session_mem.txt
      4. grep '@recent-memory:' /tmp/session_mem.txt
      5. wc -c < /tmp/session_mem.txt  # Must be ≤2000
    Expected Result: Output contains @recent-memory, total ≤2000 chars
    Evidence: .sisyphus/evidence/task-27-session-memory.txt

  Scenario: No memory directory = zero overhead
    Tool: Bash
    Steps:
      1. rm -rf .oal/state/memory
      2. echo '{}' | python3 hooks/session-start.py > /tmp/session_nomem.txt
      3. grep '@recent-memory:' /tmp/session_nomem.txt && echo 'UNEXPECTED' || echo 'CLEAN'
    Expected Result: No @recent-memory injection, CLEAN printed
    Evidence: .sisyphus/evidence/task-27-session-nomemory.txt
  ```

  **Commit**: YES (groups with Task 26)
  - Message: `feat(memory): integrate recent memory injection into session-start (on-demand)`
  - Files: `hooks/session-start.py`, `tests/test_session_start.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 28. Cognitive Mode Rules + /OAL:mode Command

  **What to do**:
  - Create 3 contextual rule files in `rules/contextual/`:
    1. `research-mode.md` — Activated when `/OAL:mode research` or architect-mode agent is in play:
       - Prioritize information gathering over implementation
       - Use librarian/explore subagents for evidence collection
       - Summarize findings before proposing solutions
       - Prefer web search + docs lookup over guessing
    2. `architect-mode.md` — Activated when `/OAL:mode architect`:
       - Think in systems, not files. Map dependencies before changes.
       - Evaluate 2-3 approaches before committing to one
       - Consider scale, maintenance, team impact
       - Use oracle subagent for strategic decisions
    3. `implement-mode.md` — Activated when `/OAL:mode implement` (DEFAULT):
       - Focus on shipping. Write code, test, verify.
       - Follow existing patterns. Don't redesign while implementing.
       - Run tests after every change. Evidence before claims.
       - Use domain-specific agent based on file types being modified.
  - Create `/OAL:mode` command (`commands/OAL:mode.md`):
    - Usage: `/OAL:mode [research|architect|implement]`
    - Writes current mode to `.oal/state/mode.txt` (plain text, one word)
    - prompt-enhancer reads `.oal/state/mode.txt` and loads corresponding contextual rule
    - Default mode (if file doesn't exist): `implement`
  - In `hooks/prompt-enhancer.py`, add mode-aware rule loading:
    ```python
    mode_path = os.path.join(project_dir, '.oal/state/mode.txt')
    mode = read_file_safe(mode_path, max_bytes=50).strip() or 'implement'
    if mode in ('research', 'architect', 'implement'):
        injections.append(f'@mode: {mode}')
    ```

  **Must NOT do**:
  - Do NOT create more than 3 mode rules.
  - Do NOT auto-switch modes. User explicitly selects.
  - Do NOT make mode persistent across sessions (session-start does NOT read mode).

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - Markdown files + simple Python integration. No complex logic.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 25-27, 29-31)
  - **Blocks**: None
  - **Blocked By**: Tasks 23, 24 (agent registry + agent definitions reference cognitive modes)

  **References**:
  - `rules/contextual/` — Existing contextual rules (follow same format)
  - `hooks/prompt-enhancer.py:170-208` — Existing mode detection (ulw/ralph/crazy). Add cognitive mode reading here.
  - `agents/oal-research-mode.md`, `agents/oal-architect-mode.md`, `agents/oal-implement-mode.md` — (from Task 24) Agent definitions that align with these modes
  - Superpowers plugin: anti-rationalization tables concept (modes enforce different thinking styles)

  **Acceptance Criteria**:
  - [x] 3 rule files exist: `rules/contextual/research-mode.md`, `architect-mode.md`, `implement-mode.md`
  - [x] `commands/OAL:mode.md` exists
  - [x] `echo 'research' > .oal/state/mode.txt && echo '{"tool_input":{"user_message":"test"}}' | python3 hooks/prompt-enhancer.py` → output contains `@mode: research`
  - [x] Missing mode file defaults to `implement`

  **QA Scenarios:**
  ```
  Scenario: Mode switch changes prompt-enhancer injection
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state
      2. echo 'research' > .oal/state/mode.txt
      3. echo '{"tool_input":{"user_message":"find auth patterns"}}' | python3 hooks/prompt-enhancer.py > /tmp/mode_research.txt
      4. grep '@mode: research' /tmp/mode_research.txt
      5. echo 'architect' > .oal/state/mode.txt
      6. echo '{"tool_input":{"user_message":"design auth system"}}' | python3 hooks/prompt-enhancer.py > /tmp/mode_architect.txt
      7. grep '@mode: architect' /tmp/mode_architect.txt
    Expected Result: Each mode reflected in prompt-enhancer output
    Evidence: .sisyphus/evidence/task-28-mode-switch.txt

  Scenario: Default mode is implement when no file exists
    Tool: Bash
    Steps:
      1. rm -f .oal/state/mode.txt
      2. echo '{"tool_input":{"user_message":"test"}}' | python3 hooks/prompt-enhancer.py > /tmp/mode_default.txt
      3. grep '@mode: implement' /tmp/mode_default.txt || echo 'DEFAULT MISSING'
    Expected Result: Default mode is 'implement'
    Evidence: .sisyphus/evidence/task-28-mode-default.txt
  ```

  **Commit**: YES
  - Message: `feat(modes): add cognitive mode rules (research/architect/implement) and /OAL:mode command`
  - Files: `rules/contextual/research-mode.md`, `rules/contextual/architect-mode.md`, `rules/contextual/implement-mode.md`, `commands/OAL:mode.md`, `hooks/prompt-enhancer.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 29. Agent Routing + Model Dispatch in prompt-enhancer.py + Circuit-Breaker v2

  **What to do**:
  - In `hooks/prompt-enhancer.py`, REPLACE the existing specialist routing (lines 209-261) with registry-based dispatch:
    ```python
    from _agent_registry import resolve_agent, get_dispatch_params, detect_available_models
    
    # Extract keywords from user prompt (already done above)
    agent = resolve_agent(set(keywords))
    if agent:
        params = get_dispatch_params(agent['name'])
        models = detect_available_models()
        preferred = agent['preferred_model']
        if preferred not in models and preferred != 'claude':
            preferred = 'claude'  # fallback
        injections.append(f'@agent-hint: {agent["description"]} | model={preferred}')
        if agent.get('mcp_tools'):
            injections.append(f'@mcp-prefer: {", ".join(agent["mcp_tools"])}')
    ```
  - **Circuit-breaker v2 enhancement** in `hooks/circuit-breaker.py`:
    1. **Domain-aware routing**: When failure detected in auth/security domain → suggest codex-cli. UI domain → suggest gemini-cli.
    2. **Progressive escalation**: Phase 1 (warning) → Phase 2 (suggest agent) → Phase 3 (force escalation) → Phase 4 (hard block)
    3. **Time-decay**: Failures older than 30 min get half-weight. Prevents old failures from triggering escalation.
    4. **Recovery memory**: When a pattern succeeds after failures, log to `.oal/state/ledger/recovery.jsonl`:
       ```json
       {"pattern":"npm test","failed_approach":"mock override","working_approach":"fixture reset","ts":"ISO8601"}
       ```
       Next time same pattern fails, suggest the working approach first.
  - **Circuit-breaker v2 domain routing table** (add to circuit-breaker.py):
    ```python
    DOMAIN_MODEL_HINTS = {
        'auth': 'codex-cli', 'security': 'codex-cli', 'crypto': 'codex-cli',
        'database': 'codex-cli', 'sql': 'codex-cli', 'migration': 'codex-cli',
        'algorithm': 'codex-cli', 'performance': 'codex-cli',
        'ui': 'gemini-cli', 'css': 'gemini-cli', 'layout': 'gemini-cli',
        'responsive': 'gemini-cli', 'design': 'gemini-cli', 'visual': 'gemini-cli',
    }
    ```

  **Must NOT do**:
  - Do NOT remove existing circuit-breaker behavior. ENHANCE it.
  - Do NOT make agent dispatch BLOCKING. It's a hint, not a requirement.
  - Do NOT call external CLIs from prompt-enhancer. Only provide hints. Task 34 handles actual dispatch.
  - Do NOT exceed 1000 chars total injection budget.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-testing`]
    - `python-testing`: Complex routing logic with multiple code paths needs thorough testing.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 25-28, 30-31)
  - **Blocks**: Task 34 (model-per-agent dispatch uses hints from this task)
  - **Blocked By**: Tasks 23 (agent registry), 12-14 (bug fixes that touch prompt-enhancer)

  **References**:

  **Pattern References**:
  - `hooks/prompt-enhancer.py:209-261` — Current specialist routing (REPLACE with registry lookup)
  - `hooks/circuit-breaker.py:1-179` — Current failure tracking (ENHANCE with domain routing, time-decay, recovery)
  - `hooks/_agent_registry.py` — (from Task 23) `resolve_agent()`, `get_dispatch_params()`, `detect_available_models()`

  **External References**:
  - claude-flow: Q-Learning router concept (simplified to static domain mapping)
  - everything-claude-code: cost-aware-llm-pipeline (model routing based on task domain)
  - compound-engineering: recovery patterns (learning from past failures)

  **WHY Each Reference Matters**:
  - `prompt-enhancer.py:209-261`: This is the EXISTING routing code being replaced. Executor must understand current logic before rewriting.
  - `circuit-breaker.py`: Full file being enhanced. Must preserve existing 2-strike rule while adding domain awareness.
  - `_agent_registry.py`: Single source of truth for agent-to-model mapping. Don't duplicate.

  **Acceptance Criteria**:
  - [x] Auth-related prompt → `@agent-hint` suggests codex-cli
  - [x] UI-related prompt → `@agent-hint` suggests gemini-cli
  - [x] Circuit-breaker failure in auth domain → suggests codex escalation
  - [x] Time-decay: 60-min-old failure weighted at 0.25 (half per 30 min)
  - [x] Recovery memory: success after failure logged to recovery.jsonl
  - [x] `python3 -m pytest tests/test_agent_routing.py tests/test_circuit_breaker.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Agent routing resolves security prompt to codex-cli
    Tool: Bash
    Steps:
      1. echo '{"tool_input":{"user_message":"fix the JWT authentication vulnerability"}}' | python3 hooks/prompt-enhancer.py > /tmp/route_security.txt
      2. grep '@agent-hint:' /tmp/route_security.txt
      3. Assert output contains 'codex-cli' or 'security'
    Expected Result: Security keywords route to codex-cli agent hint
    Evidence: .sisyphus/evidence/task-29-agent-routing-security.txt

  Scenario: Circuit-breaker v2 domain-aware escalation
    Tool: Bash
    Steps:
      1. Create 3 failure entries in failure-tracker.json for 'npm test' with auth-related context
      2. echo '{"tool_input":{"user_message":"run npm test"}}' | python3 hooks/prompt-enhancer.py > /tmp/cb_domain.txt
      3. Assert output suggests codex escalation (not generic)
    Expected Result: Domain-aware escalation suggests codex for auth failures
    Evidence: .sisyphus/evidence/task-29-circuit-breaker-domain.txt

  Scenario: Recovery memory suggests working approach
    Tool: Bash
    Steps:
      1. Create recovery.jsonl entry: {"pattern":"npm test","working_approach":"fixture reset"}
      2. Create failure for 'npm test' in failure-tracker.json
      3. echo '{"tool_input":{"user_message":"npm test is failing"}}' | python3 hooks/prompt-enhancer.py > /tmp/recovery.txt
      4. grep 'fixture reset' /tmp/recovery.txt
    Expected Result: Recovery memory suggests previously-working approach
    Evidence: .sisyphus/evidence/task-29-recovery-memory.txt
  ```

  **Commit**: YES
  - Message: `feat(routing): add registry-based agent routing, circuit-breaker v2 with domain awareness and recovery memory`
  - Files: `hooks/prompt-enhancer.py`, `hooks/circuit-breaker.py`, `tests/test_agent_routing.py`, `tests/test_circuit_breaker.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 30. Compound Learning Capture on SessionEnd

  **What to do**:
  - In `hooks/session-end-capture.py` (from Task 9/19), add Capture B (learning):
    ```python
    def capture_learnings(project_dir):
        """Extract patterns from tool ledger for compound learning."""
        ledger_path = os.path.join(project_dir, '.oal/state/ledger/tool-ledger.jsonl')
        if not os.path.exists(ledger_path): return
        
        # Read last 100 entries
        entries = []
        with open(ledger_path) as f:
            for line in f:
                try: entries.append(json.loads(line.strip()))
                except: pass
        entries = entries[-100:]
        
        # Extract patterns: repeated tool sequences, common file modifications
        tool_counts = {}
        file_counts = {}
        for e in entries:
            tool = e.get('tool', 'unknown')
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
            f = e.get('file', '')
            if f: file_counts[f] = file_counts.get(f, 0) + 1
        
        # Write learning summary
        learn_dir = os.path.join(project_dir, '.oal/state/learnings')
        os.makedirs(learn_dir, exist_ok=True)
        learn_path = os.path.join(learn_dir, f'{date_str}-{session_short}.md')
        
        with open(learn_path, 'w') as f:
            f.write(f'# Learnings: {date_str}\n')
            f.write(f'## Most Used Tools\n')
            for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1])[:5]:
                f.write(f'- {tool}: {count}x\n')
            f.write(f'## Most Modified Files\n')
            for file, count in sorted(file_counts.items(), key=lambda x: -x[1])[:5]:
                f.write(f'- {file}: {count}x\n')
    ```
  - **NO AI synthesis**. Pure counting and extraction from tool-ledger.
  - **Feature flag**: `get_feature_flag('learning')` — disabled by default.
  - **Budget**: Learning files max 300 chars each. Rotation: max 30 files.
  - **Inspired by**: compound-engineering's `learnings-researcher` (but we don't use AI, just stats).

  **Must NOT do**:
  - Do NOT call any LLM API. Statistics only.
  - Do NOT write learning files >300 chars.
  - Do NOT process ledger entries older than current session (SessionEnd provides session boundary).

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 25-29, 31)
  - **Blocks**: Task 31 (critical-patterns.md aggregation)
  - **Blocked By**: Tasks 8, 9 (dispatcher + SessionEnd skeleton)

  **References**:
  - `hooks/session-end-capture.py` — (from Tasks 9, 19) Add Capture B alongside Capture A (memory)
  - `hooks/tool-ledger.py` — JSONL entry format reference
  - compound-engineering: `learnings-researcher` concept (AI-free version)
  - `.oal/state/ledger/tool-ledger.jsonl` — Source data format

  **Acceptance Criteria**:
  - [x] After SessionEnd: `.oal/state/learnings/` contains a new .md file
  - [x] Learning file ≤300 chars
  - [x] Learning file contains "Most Used Tools" and "Most Modified Files" sections
  - [x] `python3 -m pytest tests/test_learning_capture.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Learning captured from tool ledger on SessionEnd
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/ledger .oal/state/learnings
      2. Create 10 ledger entries: 5x Write to src/auth.ts, 3x Bash npm test, 2x Read
      3. echo '{"session_id":"ses_learn","cwd":"'$(pwd)'"}' | python3 hooks/session-end-capture.py
      4. ls .oal/state/learnings/*.md | wc -l  # Should be >= 1
      5. cat .oal/state/learnings/*.md | grep 'Write'  # Most used tool
    Expected Result: Learning file created with Write as most-used tool and auth.ts as most-modified file
    Evidence: .sisyphus/evidence/task-30-learning-capture.txt

  Scenario: Empty ledger produces no learning file
    Tool: Bash
    Steps:
      1. rm -f .oal/state/ledger/tool-ledger.jsonl
      2. echo '{"session_id":"ses_empty","cwd":"'$(pwd)'"}' | python3 hooks/session-end-capture.py
      3. ls .oal/state/learnings/ 2>/dev/null | wc -l  # Should be 0 (no new file)
    Expected Result: No learning file created for empty sessions
    Evidence: .sisyphus/evidence/task-30-learning-empty.txt
  ```

  **Commit**: YES (groups with Task 31)
  - Message: `feat(learning): add compound learning capture from tool ledger on SessionEnd`
  - Files: `hooks/session-end-capture.py`, `tests/test_learning_capture.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 31. Learnings Storage + critical-patterns.md Aggregation

  **What to do**:
  - Create `hooks/_learnings.py` utility module:
    ```python
    def aggregate_learnings(project_dir, max_patterns=10) -> str:
        """Read all learning files, aggregate top patterns into summary."""
        learn_dir = os.path.join(project_dir, '.oal/state/learnings')
        if not os.path.isdir(learn_dir): return ''
        
        all_tools = {}  # tool -> total count across sessions
        all_files = {}  # file -> total count across sessions
        
        for fname in os.listdir(learn_dir):
            if not fname.endswith('.md'): continue
            content = read_file_safe(os.path.join(learn_dir, fname))
            # Parse simple '- tool: Nx' format
            for line in content.split('\n'):
                if line.startswith('- ') and ':' in line and 'x' in line:
                    parts = line[2:].rsplit(':', 1)
                    if len(parts) == 2:
                        name = parts[0].strip()
                        count = int(parts[1].strip().replace('x',''))
                        all_tools[name] = all_tools.get(name, 0) + count
        
        return format_critical_patterns(all_tools, all_files, max_patterns)
    
    def rotate_learnings(project_dir, max_files=30):
        """Delete oldest learning files if count exceeds max."""
    ```
  - Create `/OAL:learn` enhancement: When user runs `/OAL:learn auto`, read aggregated learnings to suggest patterns.
  - Create `.oal/knowledge/critical-patterns.md` auto-generation:
    - Generated on-demand when `/OAL:learn` runs (NOT on every session)
    - Contains: top 10 tool patterns, top 10 file hotspots, suggested skills
    - Max 500 chars

  **Must NOT do**:
  - Do NOT auto-generate critical-patterns.md on every session. Only when `/OAL:learn` runs.
  - Do NOT exceed 500 chars for critical-patterns.md.
  - Do NOT use AI for aggregation. Pure counting.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 25-30)
  - **Blocks**: None
  - **Blocked By**: Task 30 (learning capture creates the files to aggregate)

  **References**:
  - `hooks/_memory.py` — Follow same utility module pattern
  - `commands/OAL:learn.md` — Existing learn command (enhance with aggregated learnings)
  - compound-engineering: `critical-patterns.md` concept
  - `.oal/state/learnings/*.md` — Source files from Task 30

  **Acceptance Criteria**:
  - [x] `aggregate_learnings()` returns top patterns from multiple session files
  - [x] Rotation: >30 files → deletes oldest
  - [x] critical-patterns.md ≤500 chars
  - [x] `python3 -m pytest tests/test_learnings.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Aggregation across multiple learning files
    Tool: Bash
    Steps:
      1. mkdir -p .oal/state/learnings
      2. Create 3 learning files with overlapping tool patterns (Write: 5x, 3x, 2x across files)
      3. python3 -c "import sys; sys.path.insert(0,'hooks'); from _learnings import aggregate_learnings; r=aggregate_learnings('.'); print(r); assert 'Write' in r; assert len(r) <= 500"
    Expected Result: Write shows as top pattern with total count 10, within 500 chars
    Evidence: .sisyphus/evidence/task-31-learning-aggregate.txt

  Scenario: Rotation keeps max 30 learning files
    Tool: Bash
    Steps:
      1. Create 35 learning files in .oal/state/learnings/
      2. python3 -c "from _learnings import rotate_learnings; rotate_learnings('.')"
      3. ls .oal/state/learnings/*.md | wc -l  # Should be 30
    Expected Result: Oldest 5 files deleted, 30 remain
    Evidence: .sisyphus/evidence/task-31-learning-rotation.txt
  ```

  **Commit**: YES (groups with Task 30)
  - Message: `feat(learning): add learnings aggregation, rotation, and critical-patterns.md generation`
  - Files: `hooks/_learnings.py`, `commands/OAL:learn.md`, `tests/test_learnings.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

### Wave 5 — Optimization + Migration (Tasks 32-37)

- [x] 32. Token Budget Optimization (session-start.py)

  **What to do**:
  - Audit `hooks/session-start.py` total output and enforce hard cap:
    ```python
    MAX_SESSION_START_CHARS = 2000
    MAX_IDLE_CHARS = 200  # When no active work (no plan, no handoff, no memory)
    
    # After building all context_parts, enforce budget
    output = '\n'.join(context_parts)
    if len(output) > MAX_SESSION_START_CHARS:
        # Trim lowest-priority sections first: memory > handoff > progress > profile
        # Profile is always kept (highest priority, smallest)
        output = trim_to_budget(context_parts, MAX_SESSION_START_CHARS)
    ```
  - Add `hooks/_budget.py` constants module:
    ```python
    SESSION_START_MAX = 2000       # chars for session-start total
    SESSION_START_IDLE_MAX = 200   # chars when no active work
    PROMPT_ENHANCER_MAX = 1000     # chars for prompt-enhancer total
    MEMORY_INJECTION_MAX = 200     # chars for memory in prompt-enhancer
    RECENT_MEMORY_MAX = 150        # chars for recent memory in session-start
    KNOWLEDGE_INJECTION_MAX = 300  # chars for knowledge chunks
    PLAN_INJECTION_MAX = 100       # chars for plan reminder
    ```
  - Add budget tracking: each injection records its char count. Total validated before output.
  - **Idle detection**: If no `.oal/state/_plan.md`, no `handoff.md`, no `memory/`, inject only profile (1-liner) + tool hint = ≤200 chars.

  **Must NOT do**:
  - Do NOT remove any existing injection. Only add budget enforcement.
  - Do NOT change injection order (priority matters for trimming).

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 33-37)
  - **Blocks**: None
  - **Blocked By**: Tasks 27 (memory integration adds to budget)

  **References**:
  - `hooks/session-start.py` — Full file (203 lines) — measure current output sizes
  - `hooks/_common.py` — Add budget enforcement utilities
  - OAL README: "session-start capped at 1500 chars" (v4.2), now raise to 2000 for new features

  **Acceptance Criteria**:
  - [x] `echo '{}' | python3 hooks/session-start.py | wc -c` ≤ 2000 (always)
  - [x] Idle mode (no plan, no handoff): output ≤200 chars
  - [x] `_budget.py` exists with all constants
  - [x] `python3 -m pytest tests/test_session_start.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Idle session-start is minimal
    Tool: Bash
    Steps:
      1. rm -rf .oal/state/_plan.md .oal/state/handoff.md .oal/state/memory
      2. echo '{}' | python3 hooks/session-start.py > /tmp/idle.txt
      3. wc -c < /tmp/idle.txt
      4. Assert ≤200
    Expected Result: Idle output is ≤200 chars
    Evidence: .sisyphus/evidence/task-32-idle-budget.txt

  Scenario: Full context stays within 2000 char budget
    Tool: Bash
    Steps:
      1. Create all possible state files: profile.yaml, _plan.md, handoff.md, memory, working-memory
      2. echo '{}' | python3 hooks/session-start.py > /tmp/full.txt
      3. wc -c < /tmp/full.txt
      4. Assert ≤2000
    Expected Result: Even with all context, output ≤2000 chars
    Evidence: .sisyphus/evidence/task-32-full-budget.txt
  ```

  **Commit**: YES
  - Message: `perf(tokens): add hard budget caps to session-start.py with idle detection`
  - Files: `hooks/session-start.py`, `hooks/_budget.py`, `tests/test_session_start.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 33. Token Budget Optimization (prompt-enhancer.py)

  **What to do**:
  - Audit `hooks/prompt-enhancer.py` total injection output and enforce hard cap:
    ```python
    from _budget import PROMPT_ENHANCER_MAX
    
    # After building all injections, enforce budget
    total = sum(len(i) for i in injections)
    if total > PROMPT_ENHANCER_MAX:
        # Trim lowest-priority: memory > knowledge > agent-hint > mode > discipline
        injections = trim_injections(injections, PROMPT_ENHANCER_MAX)
    ```
  - Add per-injection budget tracking in debug mode (stderr log).
  - **Zero-injection case**: If user prompt is a simple question (no keywords match, no failures, no mode) → inject NOTHING. Zero chars. This is the most common case.
  - **Injection priority** (highest to lowest): discipline > plan-reminder > mode > agent-hint > knowledge > memory > stuck-hint.

  **Must NOT do**:
  - Do NOT change injection content. Only add budget enforcement.
  - Do NOT add injections for simple prompts. Zero overhead for basic questions.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 32, 34-37)
  - **Blocks**: None
  - **Blocked By**: Tasks 26, 28, 29 (memory + mode + routing all add injections)

  **References**:
  - `hooks/prompt-enhancer.py` — Full file (476 lines) — measure current injection sizes
  - `hooks/_budget.py` — (from Task 32) Budget constants
  - OAL README: "prompt-enhancer capped at 600 chars" (v4.2), now 1000 for new features

  **Acceptance Criteria**:
  - [x] Simple prompt (no keywords): zero injections, output = original prompt only
  - [x] Complex prompt: total injections ≤1000 chars
  - [x] `python3 -m pytest tests/test_prompt_enhancer.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Simple prompt gets zero injection
    Tool: Bash
    Steps:
      1. echo '{"tool_input":{"user_message":"hello"}}' | python3 hooks/prompt-enhancer.py > /tmp/simple.txt
      2. Assert output equals input or has minimal overhead (≤50 chars added)
    Expected Result: Near-zero injection for simple prompts
    Evidence: .sisyphus/evidence/task-33-simple-prompt.txt

  Scenario: Complex prompt stays within 1000 char budget
    Tool: Bash
    Steps:
      1. Set up all possible injection sources: mode, memory, knowledge, failures
      2. echo '{"tool_input":{"user_message":"fix the JWT auth vulnerability in the responsive layout"}}' | python3 hooks/prompt-enhancer.py > /tmp/complex.txt
      3. Measure injection size (output - input)
      4. Assert ≤1000 chars injected
    Expected Result: Total injections stay within 1000 char budget
    Evidence: .sisyphus/evidence/task-33-complex-budget.txt
  ```

  **Commit**: YES
  - Message: `perf(tokens): add hard budget caps to prompt-enhancer.py with zero-injection optimization`
  - Files: `hooks/prompt-enhancer.py`, `tests/test_prompt_enhancer.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 34. Model-Per-Agent Dispatch in runtime/team_router.py (codex-cli/gemini-cli Integration)

  **What to do**:
  - This is the **critical task** for precise tool-calling like OMC. Enhance `runtime/team_router.py` to ACTUALLY invoke external CLIs:
    ```python
    import subprocess
    from hooks._agent_registry import detect_available_models, AGENT_REGISTRY
    
    def dispatch_to_model(agent_name: str, prompt: str, project_dir: str) -> dict:
        """Dispatch a task to the preferred model for this agent."""
        agent = AGENT_REGISTRY.get(agent_name)
        if not agent: return {'error': f'Unknown agent: {agent_name}'}
        
        models = detect_available_models()
        preferred = agent['preferred_model']
        
        if preferred == 'codex-cli' and 'codex-cli' in models:
            return invoke_codex(prompt, project_dir)
        elif preferred == 'gemini-cli' and 'gemini-cli' in models:
            return invoke_gemini(prompt, project_dir)
        else:
            # Fallback: use Claude native task() dispatch
            return {'fallback': 'claude', 'category': agent.get('task_category', 'deep')}
    
    def invoke_codex(prompt: str, project_dir: str, timeout=120) -> dict:
        """Invoke codex-cli as subprocess."""
        try:
            result = subprocess.run(
                ['codex', '--quiet', '--approval-mode', 'full-auto', '-p', prompt],
                capture_output=True, text=True, timeout=timeout, cwd=project_dir
            )
            return {'model': 'codex-cli', 'output': result.stdout, 'exit_code': result.returncode}
        except subprocess.TimeoutExpired:
            return {'error': 'codex-cli timeout', 'fallback': 'claude'}
        except FileNotFoundError:
            return {'error': 'codex-cli not found', 'fallback': 'claude'}
    
    def invoke_gemini(prompt: str, project_dir: str, timeout=120) -> dict:
        """Invoke gemini-cli as subprocess."""
        try:
            result = subprocess.run(
                ['gemini', '-p', prompt],
                capture_output=True, text=True, timeout=timeout, cwd=project_dir
            )
            return {'model': 'gemini-cli', 'output': result.stdout, 'exit_code': result.returncode}
        except subprocess.TimeoutExpired:
            return {'error': 'gemini-cli timeout', 'fallback': 'claude'}
        except FileNotFoundError:
            return {'error': 'gemini-cli not found', 'fallback': 'claude'}
    ```
  - **CLI detection**: Cache `which codex` / `which gemini` result per session (avoid repeated lookups).
  - **Structured prompt packaging**: Before invoking CLI, package context:
    ```python
    def package_prompt(agent_name, user_prompt, project_dir):
        """Build structured prompt for external CLI."""
        agent = AGENT_REGISTRY[agent_name]
        return f"""You are a {agent['description']}

Project: {project_dir}
Task: {user_prompt}

Constraints: {agent.get('constraints', 'Follow existing patterns.')}"""
    ```
  - **Fallback chain**: preferred_model → claude native → error with guidance.
  - **Integration with commands**: `/OAL:escalate`, `/OAL:crazy`, `/OAL:teams` all use `dispatch_to_model()`.
  - **MCP tool awareness**: When dispatching, include which MCP tools are available in the structured prompt.

  **Must NOT do**:
  - Do NOT auto-install codex-cli or gemini-cli. Only detect and use if available.
  - Do NOT pass sensitive data (API keys, secrets) in subprocess prompts.
  - Do NOT block indefinitely. All subprocess calls have 120s timeout.
  - Do NOT run CLIs without `--quiet` / equivalent flag (prevent interactive prompts).

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`python-testing`]
    - `python-testing`: Subprocess mocking and integration testing needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 32-33, 35-37)
  - **Blocks**: None (final integration point)
  - **Blocked By**: Tasks 23, 29 (agent registry + routing hints)

  **References**:

  **Pattern References**:
  - `runtime/team_router.py` — Current dispatch logic (enhance, don't replace)
  - `hooks/_agent_registry.py` — (from Task 23) Agent definitions, model preferences
  - `commands/OAL:escalate.md` — Current escalation command (will use dispatch_to_model)
  - `commands/OAL:crazy.md` — Multi-agent orchestration (will use dispatch_to_model)

  **External References**:
  - oh-my-claudecode: team_router model dispatch pattern (codex/gemini subprocess calls)
  - oh-my-opencode: `task()` dispatch with category + skills
  - Claude Code protocol: `task()` parameters for native dispatch

  **WHY Each Reference Matters**:
  - `runtime/team_router.py`: This IS the file being enhanced. Must understand current dispatch flow.
  - OMC team_router: Proven pattern for subprocess CLI invocation with fallback.
  - `_agent_registry.py`: Source of truth for which agent prefers which model.

  **Acceptance Criteria**:
  - [x] `dispatch_to_model('frontend-designer', 'fix CSS', '.')` → attempts gemini-cli
  - [x] `dispatch_to_model('backend-engineer', 'fix auth', '.')` → attempts codex-cli
  - [x] Missing CLI → graceful fallback to claude native
  - [x] Timeout (120s) → graceful fallback
  - [x] `python3 -m pytest tests/test_team_router.py -x` → PASS

  **QA Scenarios:**
  ```
  Scenario: Model dispatch to codex-cli (or fallback if not installed)
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'runtime'); sys.path.insert(0,'hooks'); from team_router import dispatch_to_model; r=dispatch_to_model('backend-engineer','test','.');print(r)"
      2. Assert result has 'model' key (codex-cli if installed, or 'fallback':'claude')
    Expected Result: Either codex-cli invoked or graceful fallback
    Evidence: .sisyphus/evidence/task-34-model-dispatch.txt

  Scenario: Timeout handling for slow CLI
    Tool: Bash
    Steps:
      1. python3 -c "import sys; sys.path.insert(0,'runtime'); sys.path.insert(0,'hooks'); from team_router import invoke_codex; r=invoke_codex('sleep 200','.', timeout=1); print(r); assert 'timeout' in str(r).lower() or 'fallback' in str(r)"
    Expected Result: Timeout detected, fallback returned
    Evidence: .sisyphus/evidence/task-34-timeout.txt
  ```

  **Commit**: YES
  - Message: `feat(dispatch): add model-per-agent CLI dispatch with codex-cli/gemini-cli subprocess integration`
  - Files: `runtime/team_router.py`, `tests/test_team_router.py`
  - Pre-commit: `python3 -m pytest tests/ -x -q`

- [x] 35. Update OAL-setup.sh for New Features

  **What to do**:
  - Add migration steps for all new files:
    ```bash
    # New hook files
    install_hook "stop_dispatcher.py"
    install_hook "session-end-capture.py"
    install_hook "pre-tool-inject.py"
    install_hook "post-tool-failure.py"
    install_hook "_budget.py"
    install_hook "_memory.py"
    install_hook "_learnings.py"
    install_hook "_agent_registry.py"
    
    # New agent files
    for agent in frontend-designer backend-engineer security-auditor database-engineer testing-engineer infra-engineer research-mode architect-mode implement-mode; do
        install_agent "oal-${agent}.md"
    done
    
    # New command files
    install_command "OAL:ralph-start.md"
    install_command "OAL:ralph-stop.md"
    install_command "OAL:mode.md"
    
    # New rule files
    install_contextual_rule "research-mode.md"
    install_contextual_rule "architect-mode.md"
    install_contextual_rule "implement-mode.md"
    
    # New state directories
    mkdir -p ".oal/state/memory"
    mkdir -p ".oal/state/learnings"
    mkdir -p ".oal/state/ledger"
    ```
  - Update `--dry-run` to show all new files.
  - Update version check: detect v4.2 → v5.0 upgrade path.
  - Preserve existing user settings in `settings.json` during merge.

  **Must NOT do**:
  - Do NOT remove existing install logic. Only ADD new file installations.
  - Do NOT force settings.json overwrite. Use merge strategy.
  - Do NOT auto-enable new features. Feature flags default to disabled.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 32-34, 36-37)
  - **Blocks**: None
  - **Blocked By**: All Wave 0-4 tasks (setup script installs what was built)

  **References**:
  - `OAL-setup.sh` — Full install script (follow existing install_hook/install_agent patterns)
  - `scripts/settings-merge.py` — Settings merge tool

  **Acceptance Criteria**:
  - [x] `./OAL-setup.sh install --dry-run` shows all new files
  - [x] `./OAL-setup.sh update` installs new hooks, agents, commands, rules
  - [x] Existing settings preserved during merge

  **QA Scenarios:**
  ```
  Scenario: Dry-run shows all new files
    Tool: Bash
    Steps:
      1. ./OAL-setup.sh install --dry-run 2>&1 | grep -c 'stop_dispatcher\|_agent_registry\|ralph-start'
      2. Assert count >= 3
    Expected Result: Dry-run lists new hook, registry, and command files
    Evidence: .sisyphus/evidence/task-35-setup-dryrun.txt
  ```

  **Commit**: YES
  - Message: `feat(setup): update OAL-setup.sh with migration for all new features`
  - Files: `OAL-setup.sh`
  - Pre-commit: `./OAL-setup.sh install --dry-run`

- [x] 36. Update settings.json with New Hook Registrations

  **What to do**:
  - Add all new hooks to `settings.json` hook registrations:
    ```json
    {
      "hooks": {
        "Stop": [
          {"type": "command", "command": "python3 $HOME/.claude/hooks/stop_dispatcher.py"}
        ],
        "SessionEnd": [
          {"type": "command", "command": "python3 $HOME/.claude/hooks/session-end-capture.py"}
        ],
        "PreToolUse": [
          {"type": "command", "command": "python3 $HOME/.claude/hooks/pre-tool-inject.py"}
        ],
        "PostToolUseFailure": [
          {"type": "command", "command": "python3 $HOME/.claude/hooks/post-tool-failure.py"}
        ]
      }
    }
    ```
  - Update `_oal` config section with new feature flags:
    ```json
    "_oal": {
      "version": "5.0.0",
      "features": {
        "ralph_loop": true,
        "memory": false,
        "learning": false,
        "agent_routing": true,
        "circuit_breaker_v2": true,
        "simplifier": true,
        "planning_gate": true,
        "cognitive_modes": true,
        "pre_flight_guards": true
      }
    }
    ```
  - **IMPORTANT**: Do NOT move hooks out of `~/.claude/settings.json`. GitHub #10412 confirms plugin-manifest hooks don't block.

  **Must NOT do**:
  - Do NOT remove existing hook registrations. Only ADD new ones.
  - Do NOT enable memory/learning by default (disabled = false).
  - Do NOT change hook execution order for existing hooks.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 32-35, 37)
  - **Blocks**: None
  - **Blocked By**: All Wave 0-4 tasks (settings must reference what exists)

  **References**:
  - `settings.json` — Current config (221 lines). Add, don't replace.
  - Claude Code hook registration format: `{"type":"command","command":"..."}`
  - Protocol Reference: Hook event names must match exactly

  **Acceptance Criteria**:
  - [x] `python3 -c "import json; s=json.load(open('settings.json')); assert 'Stop' in s.get('hooks',{})"` → PASS
  - [x] `python3 -c "import json; s=json.load(open('settings.json')); assert s['_oal']['features']['ralph_loop']"` → PASS
  - [x] settings.json is valid JSON: `python3 -m json.tool settings.json > /dev/null`

  **QA Scenarios:**
  ```
  Scenario: All new hooks registered in settings.json
    Tool: Bash
    Steps:
      1. python3 -c "import json; s=json.load(open('settings.json')); hooks=s.get('hooks',{}); print(list(hooks.keys()))"
      2. Assert 'Stop', 'SessionEnd', 'PreToolUse', 'PostToolUseFailure' all present
    Expected Result: All 4 new hook events registered
    Evidence: .sisyphus/evidence/task-36-settings-hooks.txt
  ```

  **Commit**: YES (groups with Task 35)
  - Message: `feat(config): register all new hooks and feature flags in settings.json`
  - Files: `settings.json`
  - Pre-commit: `python3 -m json.tool settings.json > /dev/null`

- [x] 37. Update README.md with New Features

  **What to do**:
  - Update README.md sections:
    1. **Feature count**: "15 Hooks" → "19 Hooks" (add stop_dispatcher, session-end-capture, pre-tool-inject, post-tool-failure)
    2. **Agent count**: "5 Agents" → "14 Agents" (add 9 new domain + cognitive agents)
    3. **Command count**: "13 Commands" → "16 Commands" (add ralph-start, ralph-stop, mode)
    4. **Rule count**: "14 Contextual Rules" → "17 Contextual Rules" (add 3 cognitive mode rules)
    5. Add new section: **"7. Agent-Model Routing"** — explain domain agents + model assignment
    6. Add new section: **"8. Cognitive Modes"** — explain research/architect/implement
    7. Add new section: **"9. Cross-Session Memory"** — explain memsearch-style memory
    8. Update File Structure tree with new files
    9. Add new **Quick Modes** entry for `/OAL:mode`
    10. Update v5.0.0 changelog

  **Must NOT do**:
  - Do NOT rewrite sections that haven't changed.
  - Do NOT add excessive documentation. Keep sections concise.
  - Do NOT add emojis or marketing language.

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 32-36)
  - **Blocks**: None
  - **Blocked By**: All Wave 0-4 tasks (document what was built)

  **References**:
  - `README.md` — Current full documentation (update, don't rewrite)
  - All new feature files from Waves 0-4

  **Acceptance Criteria**:
  - [x] README shows correct counts: 19 Hooks, 14 Agents, 16 Commands, 17 Contextual Rules
  - [x] New feature sections exist for agent routing, cognitive modes, memory
  - [x] File structure tree includes all new files

  **QA Scenarios:**
  ```
  Scenario: README feature counts are accurate
    Tool: Bash
    Steps:
      1. grep '19 Hooks' README.md && echo 'HOOKS OK'
      2. grep '14 Agents' README.md && echo 'AGENTS OK'
      3. grep '16 Commands' README.md && echo 'COMMANDS OK'
    Expected Result: All counts match actual file counts
    Evidence: .sisyphus/evidence/task-37-readme-counts.txt
  ```

  **Commit**: YES
  - Message: `docs: update README with v5.0 features, agent routing, cognitive modes, and memory`
  - Files: `README.md`
  - Pre-commit: `grep -c '19 Hooks' README.md`

---
## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit + Protocol Compliance** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Run ALL 14 Metis acceptance criteria (AC1-AC14). Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  **Protocol compliance checks**:
  - Verify all Stop hooks output valid JSON: `{"decision":"block","reason":"..."}` or empty stdout
  - Verify all PreToolUse hooks output valid JSON per Claude Code spec
  - Verify all SessionEnd hooks are fire-and-forget (no blocking output)
  - Verify `task()` dispatch uses only valid categories: quick, deep, ultrabrain, visual-engineering, unspecified-high, unspecified-low
  - Verify all agent .md files have YAML frontmatter with `preferred_model:` field
  - Verify `settings.json` hook registrations match actual hook files
  - Verify feature flags in `_oal` section all have corresponding `get_feature_flag()` checks
  **Guardrail verification**:
  - Verify circuit-breaker v2 progressive escalation: create 5 failures, confirm Phase 1→Phase 4 progression
  - Verify pre-flight guards: attempt dangerous operations (rm -rf simulation), confirm denial
  - Verify scope drift detection: modify out-of-plan file, confirm advisory
  - Verify simplifier CHECK 7 is advisory-only: trigger it, confirm no blocking
  **Model routing verification**:
  - Verify `detect_available_models()` returns at minimum `claude`
  - Verify `dispatch_to_model()` graceful fallback when CLI not available
  - Verify MCP tool discovery reads from `~/.claude/settings.json`
  Output: `Must Have [N/N] | Must NOT Have [N/N] | AC [14/14] | Protocol [N/N] | Guardrails [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review + Regression** — `unspecified-high`
  Run `python3 -m pytest tests/ -x -q`. Review all changed `.py` files for: `as any` equivalent, empty except blocks, print() in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp). Verify all hooks use `_common.setup_crash_handler()`. Verify all state writes use atomic pattern (`.tmp` + `os.rename()`).
  **New checks**:
  - Verify `_budget.py` constants are used (not hardcoded numbers) in session-start and prompt-enhancer
  - Verify all new utility modules (`_memory.py`, `_learnings.py`, `_agent_registry.py`, `_budget.py`) have corresponding test files
  - Verify no circular imports between utility modules
  - Verify all hooks exit(0) on internal errors (crash isolation)
  - Verify no subprocess calls in hooks (except `which` for model detection)
  Output: `Tests [N pass/N fail] | Hooks [N clean/N issues] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Full Integration QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-feature integration:
  - **Ralph + Planning**: Start Ralph loop with active checklist → verify blocks mention progress → complete checklist → verify Ralph still blocks but planning gate passes
  - **Memory + Session**: Run session-end → verify memory captured → start new session → verify recent memory injected
  - **Agent Routing + Circuit-Breaker**: Trigger auth failures → verify codex-cli suggestion → trigger UI failures → verify gemini-cli suggestion
  - **Cognitive Modes + Agent Selection**: Switch to research mode → verify librarian preference → switch to implement → verify domain agent preference
  - **Token Budgets Under Load**: Enable ALL features simultaneously → verify session-start ≤2000 chars AND prompt-enhancer ≤1000 chars
  Test edge cases: corrupted state files, missing directories, hook timeouts, concurrent state writes. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT Have" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.
  **Additional checks**:
  - Verify no more than 9 new agent files (14 total with existing 5)
  - Verify memory/learning feature flags default to `false`
  - Verify no vector DB, no DAG scheduler, no AI synthesis, no web UI code exists
  - Verify all guardrails ENABLE (suggest better path) rather than LIMIT (just block)
  - Count total context overhead: idle session < 200 chars, active session < 2200 chars combined
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

Each wave gets one or more logical commits:
- **Wave 0**: `fix(hooks): add stop_hook_active guard to stop-gate.py` + `feat(test): add pytest infrastructure and baseline tests` + `feat(hooks): add feature flags and error logging`
- **Wave 1**: `refactor(hooks): extract stop_dispatcher.py multiplexer` + `feat(hooks): add SessionEnd capture and PostToolUseFailure hooks`
- **Wave 2**: `fix(commands): resolve routing bugs in OAL:crazy and OAL:deep-plan` + `fix(hooks): normalize circuit-breaker patterns and knowledge index`
- **Wave 3**: `feat(ralph): implement true Ralph loop with Stop hook blocking` + `feat(memory): implement memsearch-style session memory` + `feat(planning): add forced re-read and completion gate` + `feat(agents): add agent registry and domain agents`
- **Wave 4**: `feat(ralph): add prompt injection and escape hatch` + `feat(memory): add context:fork retrieval and session-start integration` + `feat(modes): add cognitive modes` + `feat(routing): registry-based agent routing + circuit-breaker v2` + `feat(learning): compound learning capture and aggregation`
- **Wave 5**: `perf(tokens): hard budget caps for session-start and prompt-enhancer` + `feat(dispatch): model-per-agent CLI dispatch` + `feat(setup): migration for all new features` + `feat(config): hook registrations and feature flags` + `docs: README v5.0`

Pre-commit: `python3 -m pytest tests/ -x -q` (must pass)

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
python3 -m pytest tests/ -x -q          # Expected: all green

# Token budgets
echo '{}' | python3 hooks/session-start.py | wc -c  # Expected: ≤ 2200
echo '{"tool_input":{"user_message":"test"}}' | python3 hooks/prompt-enhancer.py | wc -c  # Expected: ≤ 1200

# Ralph loop
echo '{"stop_hook_active":true}' | python3 hooks/stop-gate.py; echo $?   # Expected: 0 (no block)
echo '{"stop_hook_active":false}' | python3 hooks/stop-gate.py; echo $?  # Expected: 0 (with block decision)

# Memory
ls .oal/state/memory/*.md 2>/dev/null | wc -l  # Expected: ≥ 0 (files exist after session)

# Feature flags
grep -c '"_oal"' settings.json  # Expected: 1 (section exists)

# Hook crash isolation
echo 'INVALID' | python3 hooks/stop-gate.py; echo $?  # Expected: 0
echo 'INVALID' | python3 hooks/session-end-capture.py; echo $?  # Expected: 0
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All 14 Metis acceptance criteria pass
- [x] `python3 -m pytest tests/ -x -q` passes
- [x] Token budgets within limits
- [x] Ralph loop starts, iterates, and cancels safely
- [x] Memory captures and retrieves across sessions
- [x] Planning enforcement blocks incomplete phases
- [x] All existing commands work (no regressions)
- [x] Feature flags allow disabling each new feature independently
