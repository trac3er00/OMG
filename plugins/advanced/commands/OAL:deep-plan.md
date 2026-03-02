---
description: Deep strategic planning — understands user direction, asks smart questions, creates comprehensive plan with domain awareness
allowed-tools: Read, Write, Edit, MultiEdit, Bash(find:*), Bash(cat:*), Bash(git:*), Bash(wc:*), Bash(tree:*), Bash(mkdir:*), Bash(tee:*), Grep, Glob
argument-hint: "[feature or goal to plan]"
---

# /OAL:deep-plan — Strategic Planning with Direction Understanding

## Philosophy
Regular planning = "what steps to take."
Deep planning = "understand WHY the user wants this, WHAT direction they're heading, and HOW it fits the bigger picture."

## Step 1: Direction Discovery (MANDATORY)

Do not assume goals, constraints, or context. Extract direction from:
- user prompt
- `.oal/state/handoff.md`
- `.oal/state/ledger/failure-tracker.json`
- current repo structure and patterns

Before planning anything, understand:
1. **User's real goal** — Often the stated request is one step toward something bigger. Ask: "What's the end state you're imagining?"
2. **User's constraints** — Time, budget, existing code, team preferences, tech stack decisions already made.
3. **User's domain knowledge** — Are they expert in this domain (follow their lead) or exploring (guide them)?
4. **What they've already tried** — Check .oal/state/handoff.md, failure-tracker.json, git log.

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

If DDD reference patterns exist (see .oal/knowledge/ or existing domain modules):
- Read the reference domain FIRST
- Plan the new feature to MATCH the pattern
- Note any intentional deviations with WHY

## Step 3: Create the Deep Plan

Use Bash heredoc to write `.oal/state/_plan.md` (and `.oal/idea.yml`). Do NOT use the `Write` tool — it requires a prior Read which is unnecessary for fresh plan creation:

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
6. [ ] Security review: /OAL:security-review [affected files]

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

## Step 4.5: Codex Plan Validation (MANDATORY)

Before implementation, run a dedicated Codex validation pass on the final plan.

Checklist for Codex validation:
- ordering and dependency correctness
- hidden edge cases and rollback gaps
- security/performance blind spots
- missing verification steps

Only after applying those corrections, continue to execution.

## Step 4.6: Multi-Agent Bootstrap (MANDATORY)

After validation, launch exactly 5 planning tracks with mixed-model intent using OAL-native routing (same planning discipline as superpowers/OMC):

1. Architect track (Claude)
2. Backend track (GPT/Codex)
3. Frontend track (Gemini)
4. Security track (GPT/Codex)
5. Verification track (Claude)

Each track must return:
- concrete plan steps
- risk notes
- verification commands

Then merge outputs into a single execution checklist before implementation.

## Step 5: Generate Checklist

Convert the plan into `.oal/state/_checklist.md` with concrete steps.
Each step should be completable in ONE tool interaction (not "implement the feature").

## Integration with DDD

If this is a new domain:
1. Ask the user to write (or help write) the first domain reference
2. Extract the pattern: naming convention, data flow, error handling style
3. Document the pattern in .oal/knowledge/domain-patterns/[name].md
4. Use the pattern for ALL subsequent domains

## Idea-as-Code Contract (required)

Before leaving planning, ensure `.oal/idea.yml` exists with:
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
