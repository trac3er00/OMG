---
description: Deep strategic planning with 5-track parallel analysis (advanced plugin)
allowed-tools: Agent, Read, Write, Edit, MultiEdit, AskUserQuestion, Bash(find:*), Bash(cat:*), Bash(git:*), Bash(wc:*), Bash(tree:*), Bash(mkdir:*), Bash(tee:*), Grep, Glob
argument-hint: "[feature or goal to plan]"
---

# /OMG:deep-plan — Strategic Planning with 5-Track Parallel Analysis

This is the advanced plugin implementation of deep-plan. It uses Claude Code's native Agent tool to launch 5 specialized planning agents in parallel, then synthesizes their outputs into a unified execution plan.

## Philosophy

Regular planning = "what steps to take."
Deep planning = "understand WHY the user wants this, WHAT direction they're heading, and HOW it fits the bigger picture" — analyzed from 5 specialized perspectives simultaneously.

---

## Step 1: Direction Discovery (MANDATORY)

Before launching parallel tracks, gather essential context.

### 1.1 Read Context Sources

```bash
# Check for existing state
cat .omg/state/handoff.md 2>/dev/null || echo "No handoff"
cat .omg/state/ledger/failure-tracker.json 2>/dev/null || echo "No failures"
git log --oneline -10
```

### 1.2 Understand Direction

Extract from context:
1. **User's real goal** — Often the stated request is one step toward something bigger
2. **User's constraints** — Time, budget, existing code, tech stack decisions
3. **User's domain knowledge** — Expert (follow their lead) or exploring (guide them)
4. **What they've already tried** — Check failure tracker, git log

### 1.3 Map the Domain

```bash
# Directory structure
find . -type f \( -name "*.ts" -o -name "*.py" -o -name "*.go" \) | head -50

# Key architectural patterns
grep -rn "export class\|export function\|def \|func \|struct " src/ --include="*.{ts,py,go}" 2>/dev/null | head -30

# Existing domain boundaries
ls -la src/*/ 2>/dev/null || ls -la app/*/ 2>/dev/null || ls -la packages/*/ 2>/dev/null
```

If direction is ambiguous after exploration, ask ONE focused clarifying question.

**Good questions:**
- "I see you have a Stripe integration in /src/payment/. Are you building on that, or replacing it?"
- "Your auth uses JWT in cookies. Should the new feature respect that pattern?"
- "The DB schema has 3 user types. Does this feature apply to all of them?"

**Bad questions:**
- "What framework do you want?"
- "What's your deadline?"

---

## Step 2: Select the Best 5 Agents

**Do NOT hardcode agents.** Use the agent selector to pick the 5 most relevant agents for this specific problem:

```bash
python3 runtime/agent_selector.py "{GOAL}" --n 5
```

This scores all ~40 agents in `agents/` against the goal using keyword affinity, description overlap, and file-type hints, then returns the top 5 with diversity enforcement (no two agents from the same role group).

Review the selector output. The 5 selected agents become your 5 planning tracks.

If the selector output seems wrong (e.g., missing a critical perspective like security for an auth change), override with better choices — but justify why.

## Step 3: Launch 5 Parallel Planning Tracks

Launch all 5 agents using Claude Code's Agent tool with `run_in_background: true`.

For each selected agent, construct its prompt using the agent's specialization:

```
Agent(
  prompt: """
  You are the {AGENT_NAME} track for deep planning.
  ({AGENT_DESCRIPTION})

  GOAL: $ARGUMENTS
  CODEBASE CONTEXT: [key files and patterns discovered in Step 1]

  Produce a thorough planning analysis from YOUR specialized perspective.
  Include all sections that apply to your domain:

  1. DOMAIN ANALYSIS — What aspects of this goal fall in your domain?
  2. KEY DECISIONS — Architecture/design decisions with options, trade-offs, rationale
  3. IMPLEMENTATION PLAN — File-by-file changes, order, complexity (S/M/L)
  4. RISK MATRIX — Risks rated LOW/MEDIUM/HIGH with mitigations
  5. DEPENDENCIES — What you need from other tracks, what they need from you
  6. ACCEPTANCE CRITERIA — How to verify your domain's requirements are met

  Be specific — reference actual files and patterns.
  """,
  subagent_type: "{AGENT_SUBAGENT_TYPE}",
  run_in_background: true
)
```

---

## Step 4: Collect Track Outputs

Wait for all 5 background agents to complete. Collect their outputs.

---

## Step 5: Synthesis — Merge and Resolve Conflicts

After collecting all outputs, run synthesis to merge into a unified plan.

### Conflict Resolution Rules

1. **Security wins over convenience** — Security track's "must validate" overrides shortcuts
2. **Architecture sets boundaries** — Architecture decisions are authoritative
3. **Testing validates feasibility** — If Testing says "untestable", revisit design
4. **Cross-domain alignment** — API contracts must match data needs
5. **Risk aggregation** — Combine all risk matrices into unified assessment

### Synthesis Sections

- **Unified Architecture** — Merge structure decisions from all tracks
- **Implementation Order** — Combine all tracks into ordered steps
- **Security Requirements** — Consolidate if security agent was selected
- **Test Plan** — Integrate if testing agent was selected
- **Conflict Resolution Log** — Document conflicts and resolutions

---

## Step 6: Generate Artifacts

Generate a session slug for unique artifact paths:
```bash
python3 -c "import sys; sys.path.insert(0, 'hooks'); from _common import generate_session_slug; print(generate_session_slug())"
```

### Artifact 1: `.omg/plans/{slug}/plan.md`

```markdown
# Deep Plan: [Feature Name]
Created: [date]
CHANGE_BUDGET: [small|medium|large]

## Direction
[What the user is building toward]

## Agents Selected
- Track 1: {AGENT_1_NAME} — {AGENT_1_DESCRIPTION} (score: X.X)
- Track 2: {AGENT_2_NAME} — {AGENT_2_DESCRIPTION} (score: X.X)
- Track 3: {AGENT_3_NAME} — {AGENT_3_DESCRIPTION} (score: X.X)
- Track 4: {AGENT_4_NAME} — {AGENT_4_DESCRIPTION} (score: X.X)
- Track 5: {AGENT_5_NAME} — {AGENT_5_DESCRIPTION} (score: X.X)

## Architecture Decisions
[From architecture track]

## Implementation Plan
[Merged from all tracks]

### Phase 1: Foundation
1. [ ] [step] — [file] — [what and why]
...

### Phase 2: Core Logic
...

### Phase 3: Integration
...

### Phase 4: Verification
...

## Security Requirements
[From security track, if selected]

## Test Plan
[From testing track, if selected]

## Risk Matrix (Unified)
| Risk | Source Track | Severity | Mitigation |
|------|--------------|----------|------------|

## Conflict Resolution Log
[Conflicts and resolutions]

## Assumptions
- [Assumption 1]
...

## Rollback Plan
- [Step to revert]
...

## What Would Falsify This Plan
- [Condition that would invalidate assumptions]
...
```

### Artifact 2: `.omg/plans/{slug}/plan.json`

Machine-readable with:
- `goal`, `direction`, `change_budget`
- `agents_selected[]` with each agent's name, score, and subagent_type
- `tracks[]` with each track's output
- `phases[]` with implementation steps
- `risks[]` unified risk matrix
- `conflicts[]` resolution log

### Artifact 3: `.omg/plans/dissent.json`

Record objections, risks, and counter-arguments raised during planning.

### Artifact 4: `.omg/evidence/plan-council.json`

Planning process evidence, tool outputs, validation results.

### Artifact 5: `.omg/state/_checklist.md`

Executable checklist with atomic steps:
```markdown
# Execution Checklist

## Pre-Implementation
- [ ] Read [file1] — understand pattern
...

## Phase 1: Foundation
- [ ] Create [file] with [what]
...

## Verification
- [ ] Run: [test command]
- [ ] Run: [lint command]
...
```

---

## Step 7: Present and Iterate

Show the plan to the user, then use `AskUserQuestion`:
- question: "How would you like to proceed with this plan?"
- header: "Next step"
- options:
  - label: "Approve plan", description: "Start implementation from the generated checklist"
  - label: "Adjust scope", description: "Narrow, expand, or reprioritize the plan"
  - label: "Add constraints", description: "Share requirements or context that was missed"
  - label: "Reject plan", description: "Start over with a different approach"

Wait for user selection. Update the plan based on feedback BEFORE implementation.

---

## Business Workflow Contract

Deep-plan owns the business-style delivery workflow.

**Canonical stages:** `plan -> implement -> qa -> simulate -> final_test -> production`

**Stage aliases:**
- `planning` -> `plan`
- `implementation|build` -> `implement`
- `quality|quality_assurance` -> `qa`
- `testing|test` -> `final_test`
- `prod|deploy` -> `production`

**Rules:**
1. If user provides partial path, keep user order and append missing stages
2. If no path provided, use full canonical path
3. `production=ready` only when QA/simulation/final_test gates pass

Persist workflow into planning artifacts with structured metadata.

---

## Idea-as-Code Contract

Before leaving planning, ensure `.omg/idea.yml` exists with:
- `goal`
- `constraints[]`
- `acceptance[]`
- `risk.security[]|risk.performance[]|risk.compatibility[]`
- `evidence_required.tests[]|security_scans[]|reproducibility[]`

If missing, scaffold from template.

---

## CLI Fallback (Non-Claude-Code Hosts)

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.py}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.py" ]; then
  OMG_CLI="scripts/omg.py"
fi

python3 "$OMG_CLI" deep-plan --goal "$ARGUMENTS" --parallel-tracks
```

---

## Anti-patterns

- Do NOT skip direction discovery
- Do NOT launch tracks without codebase context
- Do NOT ignore security findings
- Do NOT resolve conflicts randomly — use resolution rules
- Do NOT produce vague steps — be specific
- Do NOT claim completion without generating artifacts
- Do NOT make architecture decisions without checking existing patterns
- Do NOT hardcode which agents to use — let the selector pick
