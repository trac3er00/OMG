---
description: Deep strategic planning — understands user direction, asks smart questions, creates comprehensive plan with domain awareness
allowed-tools: Read, Write, Edit, MultiEdit, Bash(find:*), Bash(cat:*), Bash(git:*), Bash(wc:*), Bash(tree:*), Bash(mkdir:*), Bash(tee:*), Bash(python3:*), Grep, Glob
argument-hint: "[feature or goal to plan]"
---

# /OMG:deep-plan — Strategic Planning with Direction Understanding

## Philosophy
Regular planning = "what steps to take."
Deep planning = "understand WHY the user wants this, WHAT direction they're heading, and HOW it fits the bigger picture."

## Step 1: Direction Discovery (MANDATORY)

Do not assume goals, constraints, or context. Extract direction from:
- user prompt
- `.omg/state/handoff.md`
- `.omg/state/ledger/failure-tracker.json`
- current repo structure and patterns

Before planning anything, understand:
1. **User's real goal** — Often the stated request is one step toward something bigger. Ask: "What's the end state you're imagining?"
2. **User's constraints** — Time, budget, existing code, team preferences, tech stack decisions already made.
3. **User's domain knowledge** — Are they expert in this domain (follow their lead) or exploring (guide them)?
4. **What they've already tried** — Check .omg/state/handoff.md, failure-tracker.json, git log.

If direction is still ambiguous after repo exploration, ask only minimal focused questions.

Examples of BAD questions: "What framework do you want?" "What's your deadline?"
Examples of GOOD questions:
- "I see you have a Stripe integration started in /src/payment/. Are you building on that, or replacing it?"
- "Your auth uses JWT in cookies. Should the new feature respect that pattern, or are you migrating to sessions?"
- "The DB schema has 3 user types. Does this feature apply to all of them or just one?"

## Step 2: Map the Domain

Read the codebase to understand the CURRENT state:
```bash
# Directory structure
find . -type f -name "*.ts" -o -name "*.py" -o -name "*.go" | head -50

# Key architectural patterns
grep -rn "export class\|export function\|def \|func \|struct " src/ --include="*.{ts,py,go}" | head -30

# Existing domain boundaries
ls -la src/*/  # or app/*/ or packages/*/

# Data flow
grep -rn "import.*from\|require(" src/ --include="*.{ts,js}" | head -20
```

If DDD reference patterns exist (see .omg/knowledge/ or existing domain modules):
- Read the reference domain FIRST
- Plan the new feature to MATCH the pattern
- Note any intentional deviations with WHY

## Step 3: Create the Deep Plan

Use Bash heredoc to write `.omg/state/_plan.md` (and `.omg/idea.yml`). Do NOT use the `Write` tool — it requires a prior Read which is unnecessary for fresh plan creation:

```markdown
# Deep Plan: [Feature Name]
Created: [date]
CHANGE_BUDGET=[small|medium|large]

## Direction
[1-2 sentences: what the user is building toward, not just this task]

## Domain Context
Reference pattern: [file/module that sets the pattern]
Bounded contexts affected: [list]
Key interfaces: [list the interfaces/types this touches]

## Architecture Decisions
- [Decision]: [chosen approach] because [reason]
  Alternatives considered: [what was rejected and why]

## Implementation Plan

### Phase 1: Foundation [N files, ~M lines]
1. [ ] [specific action] — [file] — [what and why]
2. [ ] [specific action] — [file]

### Phase 2: Core Logic [N files, ~M lines]
3. [ ] [specific action]
4. [ ] [specific action]

### Phase 3: Integration + Security [N files, ~M lines]
5. [ ] [specific action]
6. [ ] Security review: /OMG:security-review [affected files]

### Phase 4: Verification
7. [ ] Tests: [what to test, how]
8. [ ] Edge cases: [list]
9. [ ] Manual verification: [steps]

## Risk Map
- [Risk]: [mitigation]
- [Risk]: [mitigation]

## What NOT to Do
- [Anti-pattern specific to this feature]
- [Approach that looks tempting but will fail because...]

## Files to Read Before Starting
1. [file] — [why: contains the reference pattern]
2. [file] — [why: defines the interface this must implement]
```

## Step 4: Present and Iterate

Show the plan to the user. Ask:
- "Does this match the direction you're thinking?"
- "Anything I'm missing about your goals?"
- "Should I adjust the scope or priority?"

Update the plan based on feedback BEFORE starting implementation.

## Step 4.5: Claude vs Codex Debate (MANDATORY)

Adversarial debate produces stronger plans than parallel tracks. Two models argue their planning approaches, and the best ideas from both sides survive. Intellectual conflict forces each side to sharpen and justify their position — weaknesses get exposed and the merged result is harder to break.

### Code Name Assignment

Before the debate starts, assign each side a unique tactical code name from the pool below. Pick two at random. They MUST be different. Announce: **"This debate: [NAME-A] (Claude) vs [NAME-B] (Codex)."**

```
CODE_NAMES = [
  ALPINE, OBSIDIAN, VIPER, THUNDER, FALCON, GRANITE,
  PHANTOM, HORIZON, SENTINEL, ECLIPSE, ARCTIC, IRONSIDE,
  MERIDIAN, ONYX, RAPTOR, SUMMIT
]
```

The code names are used as the debater's identity throughout all three rounds — label every argument block with the assigned code name.

### Debate Topic

The debate covers the PLAN itself — each side argues for their approach to the user's goal:
- Architecture decisions (which patterns, which abstractions)
- Implementation strategy (phases, ordering, dependencies)
- Technology/library choices (if applicable)
- Risk assessment (what could go wrong, how to prevent it)

### Round 1 — Opening Arguments (parallel dispatch)

Claude generates its opening argument. Codex is dispatched in parallel:

```python
# Claude: generate opening argument inline
# Codex: dispatch via established OMG escalation pattern
/OMG:escalate codex "You are debating a software plan. Your code name is [NAME-B].
Plan context: [paste the plan from Step 3 here]
Generate your Opening Argument for this plan using the template below.
Be specific, cite trade-offs, and argue why your approach is superior."
```

Each argument MUST follow this template:

```
## [CODE_NAME] — Opening Argument
**Position**: [1-2 sentence thesis on how to approach this plan]
**Architecture**: [proposed structure, patterns, abstractions]
**Implementation Strategy**: [phases, ordering, key dependencies]
**Risk Assessment**: [top 3 risks + mitigations]
**Key Advantage**: [why this approach outperforms alternatives]
```

### Round 2 — Rebuttals (sequential)

Each side reads the opponent's Opening Argument, then attacks its weaknesses and defends its own position.

```python
# Claude: read Codex's opening, write rebuttal
# Codex: read Claude's opening, dispatch rebuttal
/OMG:escalate codex "You are [NAME-B] in a plan debate. Your opponent [NAME-A] argued: [paste Claude opening].
Write your Rebuttal using the template below. Be specific — cite exact weaknesses."
```

Each rebuttal MUST follow this template:

```
## [CODE_NAME] — Rebuttal
**Opponent's Weaknesses**: [specific critiques of the other side's Opening]
**Defended Position**: [how own approach addresses opponent's critiques]
**Concessions**: [what the opponent got RIGHT — intellectual honesty required]
**Updated Proposal**: [refined approach incorporating valid opponent points]
```

> **Consensus Shortcut**: If after Round 1 both positions are >80% aligned (same architecture, same strategy, same risk assessment) — skip directly to the Merge Pass. No point debating identical approaches.

### Round 3 — Final Positions (sequential)

Each side reads both Rebuttals, then writes their final consolidated position.

```python
# Claude: read both rebuttals, consolidate
# Codex: read both rebuttals, dispatch final
/OMG:escalate codex "You are [NAME-B] in the final round. After the rebuttals:
[NAME-A] rebuttal: [paste Claude rebuttal]
[NAME-B] rebuttal: [paste Codex rebuttal]
Write your Final Position using the template below."
```

Each final position MUST follow this template:

```
## [CODE_NAME] — Final Position
**Consolidated Approach**: [the refined plan after all arguments]
**Incorporated from Opponent**: [specific ideas adopted from the other side]
**Non-Negotiables**: [positions that survived all challenges]
**Proposed Execution Steps**: [concrete numbered steps, actionable]
```

> **Codex Fallback**: If Codex is unavailable (timeout, auth failure, CLI error) — Claude enters **Steel-Man Mode**: generate the strongest OPPOSING argument to your own position, argue against yourself across all 3 rounds, then proceed to merge. This ensures adversarial rigor even without Codex.

### Merge Pass — Sequential-Thinking Synthesis

After Round 3 (or after the Consensus Shortcut), run a `sequential-thinking` merge pass across all debate output.

Score each argument and proposed step from both sides:
- **Feasibility** (0-3): Can this actually be implemented in this codebase?
- **Risk Coverage** (0-3): Does it address failure modes and edge cases?
- **Specificity** (0-3): Are steps concrete and actionable — not vague?
- **Codebase Consistency** (0-3): Does it match existing patterns and conventions?

Merge protocol:
- For each architectural decision point — pick the argument with the highest total score
- For complementary (non-conflicting) ideas from both sides — merge both into the output
- Score by argument quality, not volume — one strong argument beats ten weak ones
- Output: ONE unified plan that takes the best from [NAME-A] and [NAME-B]

The merged output **replaces** the plan written in Step 3 (overwrite `.omg/state/_plan.md`).

Save the full debate transcript (all 3 rounds + merge output) to `.omg/state/debate-transcript.md` for audit trail.

## Step 5: Generate Checklist

Convert the plan into `.omg/state/_checklist.md` with concrete steps.
Each step should be completable in ONE tool interaction (not "implement the feature").

## Step 5.5: Business Workflow Contract (MANDATORY)

Deep-plan owns the business-style delivery workflow and task-plan contract.

Always generate a normalized workflow path and task plan directly from user instructions:

- canonical stages: `plan -> implement -> qa -> simulate -> final_test -> production`
- accepted user path keys: `workflow`, `path`, `delivery_path`, `workflow_path`
- accepted stage aliases:
  - `planning -> plan`
  - `implementation|build -> implement`
  - `quality|quality_assurance -> qa`
  - `testing|test -> final_test`
  - `prod|deploy -> production`

Rules:
1. If user provides a partial path, keep user order and append missing canonical stages.
2. If user provides no path, use the full canonical path.
3. Build tasks from:
   - `user_instructions[]` (source of truth for requested workflow)
   - `constraints[]` (delivery boundaries)
   - `acceptance[]` (final test criteria)
4. Include stage readiness for production handoff:
   - `production=ready` only when QA/simulation/final_test gates pass.

Persist this contract into planning artifacts:
- `.omg/state/_plan.md` (human-readable plan)
- `.omg/state/_checklist.md` (atomic execution items)
- include structured task metadata in the plan output (`stage`, `title`, `detail`, `source`).

## Integration with DDD

If this is a new domain:
1. Ask the user to write (or help write) the first domain reference
2. Extract the pattern: naming convention, data flow, error handling style
3. Document the pattern in .omg/knowledge/domain-patterns/[name].md
4. Use the pattern for ALL subsequent domains

## Idea-as-Code Contract (required)

Before leaving planning, ensure `.omg/idea.yml` exists with:
- `goal`
- `constraints[]`
- `acceptance[]`
- `risk.security[]|risk.performance[]|risk.compatibility[]`
- `evidence_required.tests[]|security_scans[]|reproducibility[]`

If missing, scaffold from template and fill from the conversation.

## Anti-patterns
- Don't plan in your head and dump a wall of text — INTERACT with the user
- Don't make architecture decisions without checking existing patterns
- Don't create a plan with vague steps like "implement feature" — be specific
- Don't skip the Direction step — it's the difference between useful and useless
