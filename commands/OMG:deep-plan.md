---
description: Deep strategic planning with 5-track parallel analysis
allowed-tools: Agent, Read, Grep, Glob, AskUserQuestion, Bash(python3:*), Bash(git:*)
argument-hint: "goal or problem statement"
---

# /OMG:deep-plan — 5-Track Strategic Planning

Deep planning analyzes a problem from 5 specialized perspectives in parallel to produce a unified, executable plan.

## Step 1: Direction Discovery

Gather context before launching parallel tracks:
- Read user prompt, `.omg/state/handoff.md`, failure tracker
- Quick codebase scan: `ls -la`, `git log --oneline -10`
- Understand user's goal, constraints, and prior attempts

If direction is ambiguous, ask ONE clarifying question before proceeding.

## Step 2: Select the Best 5 Agents

**Do NOT hardcode agents.** Use the agent selector to pick the 5 most relevant agents for this specific problem:

```bash
python3 runtime/agent_selector.py "{GOAL}" --n 5
```

This scores all ~40 agents in `agents/` against the goal using keyword affinity, description overlap, and file-type hints, then returns the top 5 with diversity enforcement (no two agents from the same role group).

Review the selector output. The 5 selected agents become your 5 planning tracks.

If the selector output seems wrong (e.g., missing a critical perspective like security for an auth change), override with better choices — but justify why.

## Step 3: Launch 5 Parallel Planning Tracks

Launch all agents simultaneously with `run_in_background: true`.

For each selected agent, construct its prompt using the agent's specialization:

```
Agent(
  prompt: "Deep planning analysis from {AGENT_NAME} perspective for: {GOAL}

  You are the {AGENT_NAME} ({AGENT_DESCRIPTION}).

  Analyze this goal from your specialized perspective. Provide a thorough
  planning analysis within YOUR domain of expertise.

  Output sections (include all that apply to your domain):
  1. **Domain Analysis**: What aspects of this goal fall in your domain?
  2. **Key Decisions**: Architecture/design decisions with options, trade-offs, rationale
  3. **Implementation Plan**: File-by-file changes, order, complexity (S/M/L)
  4. **Risk Matrix**: Risks rated LOW/MEDIUM/HIGH with mitigations
  5. **Dependencies**: What you need from other tracks, what they need from you
  6. **Acceptance Criteria**: How to verify your domain's requirements are met",
  subagent_type: "{AGENT_SUBAGENT_TYPE}",
  run_in_background: true
)
```

## Step 4: Synthesis

Collect all track outputs and merge them into a unified plan.

**Conflict resolution rules:**
1. Security wins over convenience
2. Architecture sets boundaries
3. Testing validates feasibility
4. Cross-domain alignment required
5. Risk aggregation across tracks

**Synthesis sections:**
- Unified Architecture
- Implementation Order
- Security Requirements (if security agent was selected)
- Test Plan (if testing agent was selected)
- Conflict Resolution Log

### Output Format

```markdown
# Deep Plan: {GOAL}

## Agents Selected
- Track 1: {AGENT_1_NAME} — {AGENT_1_DESCRIPTION} (score: X.X)
- Track 2: {AGENT_2_NAME} — {AGENT_2_DESCRIPTION} (score: X.X)
- Track 3: {AGENT_3_NAME} — {AGENT_3_DESCRIPTION} (score: X.X)
- Track 4: {AGENT_4_NAME} — {AGENT_4_DESCRIPTION} (score: X.X)
- Track 5: {AGENT_5_NAME} — {AGENT_5_DESCRIPTION} (score: X.X)

## Unified Plan
[Synthesized plan from all tracks]

## Conflicts & Resolutions
[Where tracks disagreed and how conflicts were resolved]
```

## Step 5: Generate Artifacts

Generate a session slug for unique artifact paths:
```bash
python3 -c "import sys; sys.path.insert(0, 'hooks'); from _common import generate_session_slug; print(generate_session_slug())"
```

Create planning artifacts using the slug:
1. `.omg/plans/{slug}/plan.md` — comprehensive plan with phases
2. `.omg/plans/{slug}/plan.json` — machine-readable version
3. `.omg/state/_checklist.md` — executable checklist

## Step 6: Present and Iterate

Show the plan to the user, then use `AskUserQuestion`:
- question: "How would you like to proceed with this plan?"
- header: "Next step"
- options:
  - label: "Approve plan", description: "Start implementation from the generated checklist"
  - label: "Adjust scope", description: "Narrow, expand, or reprioritize the plan"
  - label: "Add constraints", description: "Share requirements or context that was missed"
  - label: "Reject plan", description: "Start over with a different approach"

Wait for user selection. Update plan before implementation.

## CLI Fallback

For non-Claude-Code hosts:
```bash
python3 scripts/omg.py deep-plan --goal "$ARGUMENTS" --parallel-tracks
```

## Anti-patterns

- Do NOT skip direction discovery
- Do NOT launch tracks without codebase context
- Do NOT ignore security findings
- Do NOT produce vague steps
- Do NOT claim completion without all 3 artifacts
- Do NOT hardcode which agents to use — let the selector pick
