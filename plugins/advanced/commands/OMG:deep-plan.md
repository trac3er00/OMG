---
description: Deep strategic planning — understands user direction, asks smart questions, creates comprehensive plan with domain awareness
allowed-tools: Read, Write, Edit, MultiEdit, Bash(find:*), Bash(cat:*), Bash(git:*), Bash(wc:*), Bash(tree:*), Bash(mkdir:*), Bash(tee:*), Grep, Glob
argument-hint: "[feature or goal to plan]"
---

# /OMG:deep-plan — Strategic Planning with Direction Understanding

## Philosophy
Regular planning = "what steps to take."
Deep planning = "understand WHY the user wants this, WHAT direction they're heading, and HOW it fits the bigger picture."

This command is the public compatibility path to the canonical `plan-council` bundle.
Users invoke `/OMG:deep-plan`; the runtime routes to `plan-council` for execution.

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

## Step 3: Create the Deep Plan (Plan Council Artifacts)

Generate the canonical `plan-council` artifacts. Use Bash heredoc to write these files.
Required artifacts: `.omg/plans/deep-plan.md`, `.omg/plans/deep-plan.json`, `.omg/plans/dissent.json`, `.omg/evidence/plan-council.json`.

### Artifact 1: `.omg/plans/deep-plan.md` (Human-readable)
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

### Phase 3: Integration + Verification [N files, ~M lines]
5. [ ] [specific action]
6. [ ] Verification: /OMG:security-check [affected files]

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

## Plan Council Requirements
### Assumptions
List your assumptions below:
- [Assumption 1]
- [Assumption 2]

### Objections and Dissent
Record any objections or dissent:
- [Dissent 1]
- [Dissent 2]

### Rollback Plan
Define the rollback plan:
- [Step 1 to revert]
- [Step 2 to revert]

### Verification Commands
List the verification commands:
- [Command 1]
- [Command 2]

### Evidence Requirements
Define the evidence requirements:
- [Requirement 1]
- [Requirement 2]

### What would falsify this plan?
Define what would falsify this plan:
- [Condition 1]
- [Condition 2]
```

### Artifact 2: `.omg/plans/deep-plan.json` (Machine-readable)
Include the full task plan, workflow stages, and metadata.

### Artifact 3: `.omg/plans/dissent.json` (Dissent log)
Record all objections, risks, and counter-arguments raised during planning.

### Artifact 4: `.omg/evidence/plan-council.json` (Planning evidence)
Record the planning process evidence, including tool outputs and validation results.

## Step 4: Present and Iterate

Show the plan to the user. Ask:
- "Does this match the direction you're thinking?"
- "Anything I'm missing about your goals?"
- "Should I adjust the scope or priority?"

Update the plan based on feedback BEFORE starting implementation.

## Step 4.1: Classification Boundary User Override (N8.4)

At classification boundaries, use AskUserQuestion to let the user override NEEDED/NICE/NOT-NEEDED classifications before proceeding.

When you've classified plan items, present the classification to the user with:
```
I've classified the plan items as:

NEEDED:
- [item 1] — [rationale]
- [item 2] — [rationale]

NICE-TO-HAVE:
- [item 3] — [rationale]

NOT-NEEDED:
- [item 4] — [rationale]

Do you want to override any classifications? (yes/no)
```

If user says yes, ask which items to reclassify and update the plan accordingly.

## Step 4.5: Codex Plan Validation (MANDATORY)

Before implementation, run a dedicated Codex validation pass on the final plan.

Checklist for Codex validation:
- ordering and dependency correctness
- hidden edge cases and rollback gaps
- security/performance blind spots
- missing verification steps

Only after applying those corrections, continue to execution.

## Step 4.6: Multi-Agent Bootstrap (MANDATORY)

After validation, launch exactly 5 planning tracks with mixed-model intent using OMG-native routing (same planning discipline as OMG):

1. Architect track (Claude)
2. Backend track (GPT/Codex)
3. Frontend track (Gemini)
4. Security track (GPT/Codex)
5. Verification track (Claude)

Dispatch pattern is mandatory: all 5 tracks launch in parallel as background sub-agents.

```python
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Architect planning track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Backend planning track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Frontend planning track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Security planning track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Verification planning track", prompt="...")
```

Collection and merge protocol:
- collect every track using `background_output(task_id="...")`
- run a `sequential-thinking` merge pass to resolve conflicts and ordering
- emit one final executable checklist only after the merge pass

Each track must return:
- concrete plan steps
- risk notes
- verification commands

Then merge outputs into a single execution checklist before implementation.

## Step 5: Generate Checklist

Convert the plan into `.omg/state/_checklist.md` with concrete steps.
Each step should be completable in ONE tool interaction (not "implement the feature").

After generating the checklist, proceed to Step 5.1 (Post-Plan Flow).

## Step 5.1: Post-Plan Flow — User Choice (N8.6)

After deep-plan completes (all artifacts generated, classification approved, checklist ready), use AskUserQuestion with 3 options:

```
The deep plan is ready. What would you like to do next?

1. Start implementing — Begin execution via /OMG:start-work
2. Add more items to this plan — Extend the plan with new items (incremental merge)
3. Validate plan with another model — Send to Codex/Gemini for review (if detected)

Please choose 1, 2, or 3.
```

Handle each choice:
- **Choice 1**: Invoke `/OMG:start-work` to begin implementation.
- **Choice 2**: Trigger the "Add More" loop (see Step 5.2).
- **Choice 3**: Trigger external validation (see Step 5.3).

## Step 5.2: Add More Items Loop (N8.7)

When the user selects "Add more items to this plan":

1. Ask the user: "What new items would you like to add to the plan?"
2. Run deep-plan ONLY on the NEW items:
   - Apply direction discovery to the new items
   - Map domain context for the new items
   - Classify the new items (NEEDED/NICE/NOT-NEEDED)
   - Ask user to confirm/override classifications
3. Merge the new items into the existing plan:
   - Insert into appropriate phases (Foundation, Core Logic, Integration, Verification)
   - Update file counts and line estimates
   - Renumber checklist items
   - Append to dissent.json if new objections arise
   - Update plan-council.json with merge evidence
4. Present the updated plan to the user
5. Ask the post-plan flow question again (Step 5.1)

**Critical**: Do NOT regenerate the entire plan. Only process new items and merge them into existing phases/checklist.

## Step 5.3: External Validation (N8.8)

When the user selects "Validate plan with another model":

1. Detect available AI CLIs:
   ```bash
   which codex 2>/dev/null && echo "Codex detected"
   which gemini 2>/dev/null && echo "Gemini detected"
   which gpt 2>/dev/null && echo "GPT detected"
   ```

2. If Codex CLI is detected, offer to send the plan for validation:
   ```
   I can send this plan to Codex for validation. Codex will review for:
   - Backend/security feasibility
   - Risk gaps and missing edge cases
   - Implementation order correctness
   - Rollback plan completeness

   Send plan to Codex? (yes/no)
   ```

3. If yes, dispatch the plan to Codex:
   ```bash
   codex "Review this deep plan for feasibility, risks, and gaps. Focus on backend logic, security implications, and edge cases. Provide a verdict with specific recommendations." < .omg/plans/deep-plan.md
   ```

4. Capture Codex's response and append to the plan as a new section:
   ```markdown
   ## External Validation — Codex Review
   Date: [timestamp]

   [Codex response]

   ### Verdict
   [Approved | Approved with changes | Needs rework]

   ### Action Items from Validation
   - [Item 1]
   - [Item 2]
   ```

5. Update `.omg/evidence/plan-council.json` with validation evidence.

6. If Gemini CLI is detected, offer similar validation for UX/docs items.

7. After validation is complete, ask the post-plan flow question again (Step 5.1).

## Step 5.4: Multi-Model Deep Plan (N8.9)

When multiple AI CLIs are detected during initial planning, offer multi-model planning:

```
I've detected multiple AI CLIs available:
- Codex (backend/security validation)
- Gemini (UX/visual review)

Would you like to use multi-model planning? (yes/no)

Multi-model planning means:
- Claude orchestrates the plan structure and direction
- Codex validates backend logic, security, and feasibility
- Gemini reviews UX implications and documentation clarity
```

If yes, coordinate multi-model planning:

1. **Claude** (orchestrator):
   - Direction discovery
   - Domain mapping
   - Plan structure generation
   - Classification and merge

2. **Codex** (backend/security validator):
   - Send backend-related plan items to Codex
   - Request validation for security implications, edge cases, rollback plans
   - Capture feedback and integrate into plan

3. **Gemini** (UX/docs reviewer):
   - Send UX/docs-related plan items to Gemini
   - Request review for visual consistency, accessibility, documentation clarity
   - Capture feedback and integrate into plan

4. Merge all feedback into the final plan artifacts.

5. Record multi-model evidence in `.omg/evidence/plan-council.json`.

## Step 5.5: Multi-Model Research (N8.10)

During direction discovery (Step 1), if multiple AI CLIs are detected, dispatch research in parallel:

1. Identify research questions from the user's prompt and repo exploration:
   - "How does the existing auth pattern work?"
   - "What's the current data flow for payments?"
   - "Are there existing UX patterns for modals in this codebase?"

2. Dispatch research to detected CLIs in parallel:
   ```bash
   # Example: parallel research dispatch
   codex "Analyze the auth pattern in src/auth/. How does JWT handling work? What security assumptions are made?" &
   gemini "Review the modal components in src/components/. What UX patterns are established? Are they accessible?" &
   wait
   ```

3. Collect research outputs from each CLI.

4. Synthesize findings into the "Domain Context" and "Architecture Decisions" sections of the plan.

5. Record research evidence in `.omg/evidence/plan-council.json`.

**Trigger condition**: Only dispatch multi-model research if:
- Multiple CLIs are detected
- User has not explicitly requested single-model planning
- The planning task involves both backend AND frontend concerns

## Step 5.6: Business Workflow Contract (MANDATORY)

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
- `.omg/plans/deep-plan.md` (human-readable plan)
- `.omg/plans/deep-plan.json` (machine-readable plan)
- include structured task metadata in the plan output (`stage`, `title`, `detail`, `source`).

## Step 6: Integration with DDD

If this is a new domain:
1. Ask the user to write (or help write) the first domain reference
2. Extract the pattern: naming convention, data flow, error handling style
3. Document the pattern in .omg/knowledge/domain-patterns/[name].md
4. Use the pattern for ALL subsequent domains

## Step 7: Idea-as-Code Contract (required)

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
