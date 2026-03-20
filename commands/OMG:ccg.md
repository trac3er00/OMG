---
description: CCG mode — 3-track parallel synthesis using Claude Code's native Agent tool
allowed-tools: Agent, Read, Grep, Glob, AskUserQuestion, Bash(python3:*), Bash(git:*)
argument-hint: "problem statement"
---

# /OMG:ccg — Tri-Track Parallel Synthesis

Run 3 parallel analysis tracks and synthesize into unified execution plan.

## Step 1: Parse Problem Statement

Extract the problem from ARGUMENTS. If empty or unclear, ask the user for clarification before proceeding.

```
PROBLEM = [ARGUMENTS or user's stated problem]
```

## Step 2: Select the Best 3 Agents

**Do NOT hardcode agents.** Use the agent selector to pick the 3 most relevant agents for this specific problem:

```bash
python3 runtime/agent_selector.py "{PROBLEM}" --n 3
```

This scores all ~40 agents in `agents/` against the problem statement using keyword affinity, description overlap, and file-type hints, then returns the top 3 with diversity enforcement (no two agents from the same role group).

Review the selector output. The 3 selected agents become Track 1, Track 2, and Track 3.

If the selector output seems wrong for this problem (e.g., all 3 are review-only agents for an implementation task), override with better choices — but justify why.

## Step 3: Launch 3 Parallel Agents

Use Claude Code's native Agent tool to launch all 3 tracks in parallel with `run_in_background: true`.

For each selected agent, construct its prompt using the agent's specialization:

```
Agent(
  prompt: "{AGENT_NAME} analysis for: {PROBLEM}

  You are the {AGENT_NAME} ({AGENT_DESCRIPTION}).

  Analyze this problem from your specialized perspective.
  Focus on what falls within YOUR domain.

  Output format:
  ## {AGENT_NAME} Analysis
  ### Key Findings
  [findings specific to your domain]
  ### Risks & Concerns
  [domain-specific risks with mitigations]
  ### Implementation Steps
  [ordered list with file paths, scoped to your domain]
  ### Dependencies on Other Tracks
  [what you need from the other tracks, or what they need from you]",
  subagent_type: "{AGENT_SUBAGENT_TYPE}",
  run_in_background: true
)
```

## Step 4: Collect All Results

Wait for all 3 background agents to complete. Collect their outputs.

## Step 5: Synthesize Unified Plan

After all tracks complete, synthesize results into a single execution plan:

1. **Identify conflicts** — Where do tracks disagree?
2. **Resolve conflicts** — Use the most authoritative track for each domain as tiebreaker
3. **Merge implementation steps** — Combine into one ordered list respecting dependencies
4. **Consolidate risks** — Deduplicate and prioritize risks from all tracks

### Output Format

```markdown
# CCG Synthesis: {PROBLEM}

## Agents Selected
- Track 1: {AGENT_1_NAME} — {AGENT_1_DESCRIPTION} (score: X.X)
- Track 2: {AGENT_2_NAME} — {AGENT_2_DESCRIPTION} (score: X.X)
- Track 3: {AGENT_3_NAME} — {AGENT_3_DESCRIPTION} (score: X.X)

## Consensus
[What all tracks agree on]

## Conflicts Resolved
[Any disagreements and how they were resolved]

## Unified Execution Plan

### Phase 1: Foundation
1. [ ] [action] — [file] — [rationale]
2. [ ] [action] — [file] — [rationale]

### Phase 2: Core Implementation
3. [ ] [action] — [file] — [rationale]
...

### Phase 3: Integration
N. [ ] [action] — [file] — [rationale]

### Phase 4: Verification
- [ ] Tests: [specific test commands]
- [ ] Security: [checks to run]
- [ ] Manual: [verification steps]

## Risk Summary
- [Risk 1]: [mitigation]
- [Risk 2]: [mitigation]

## Rollback Plan
[Steps to revert if needed]
```

## Step 6: Present to User

Present the unified plan, then use `AskUserQuestion`:
- question: "How would you like to proceed with this plan?"
- header: "Next step"
- options:
  - label: "Approve plan", description: "Start implementation from the execution plan"
  - label: "Adjust plan", description: "Modify scope, priority, or approach"
  - label: "Re-run a track", description: "Re-analyze one specific perspective"
  - label: "Reject plan", description: "Start over with a different approach"

Wait for user selection before proceeding.

---

## CLI Fallback (non-Claude-Code hosts)

For environments without native Agent tool, use the OMG runtime:

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.py}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.py" ]; then OMG_CLI="scripts/omg.py"; fi
python3 "$OMG_CLI" ccg --problem "[ARGUMENTS]"
```
