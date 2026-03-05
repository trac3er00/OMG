---
description: "CRAZY mode — maximum multi-agent orchestration. Claude orchestrates, Codex deep-codes, Gemini designs. Anti-hallucination + error-loop prevention."
allowed-tools: Read, Write, Edit, MultiEdit, Bash, Grep, Glob, Task
argument-hint: "[task description]"
---

# /OMG:crazy — All-Agent Maximum Orchestration

## Phase 1: Intent Classification (BEFORE acting)

STOP. Before doing ANYTHING, say out loud:
"I understand you want me to [INTENT]: [specific goal]."

| Signal | Intent | Action |
|--------|--------|--------|
| fix/bug/error | **FIX** | Debug → patch source → verify |
| build/create/add | **IMPLEMENT** | Plan → code → test |
| refactor/clean | **REFACTOR** | Preserve behavior, verify before+after |
| review/check | **REVIEW** | Read ALL → report → don't change |

If the user hasn't confirmed, ASK. Don't assume.

## Phase 1.5: Brainstorm Merge (AUTOMATIC)

CRAZY mode now includes brainstorming by default. Do not run a separate brainstorm command.

- Generate 2-3 viable approaches quickly
- Compare trade-offs (risk, effort, reversibility)
- Pick one approach and proceed immediately

## Phase 2: Agent Dispatch (Parallel Sub-Agent Required)

CRAZY mode must use parallel sub-agent dispatch for worker tracks.

### Mandatory parallel launch pattern

```python
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Architect track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Backend track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Frontend track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Security track", prompt="...")
task(subagent_type="explore", run_in_background=true, load_skills=[], description="Verification track", prompt="...")
```

Then:
- collect each task with `background_output(task_id="...")`
- run a `sequential-thinking` synthesis pass to merge contradictions and produce one dependency-ordered checklist
- only then start implementation

### Claude (You — Orchestrator)
- Break task into parallel subtasks
- Delegate to specialists
- Synthesize results
- Make architecture decisions
- Run a sequential-thinking merge before implementation

### Codex — Deep Worker + Code Reviewer
**Codex=deep-code: backend logic, security, debugging, algorithms, performance, root cause analysis**
Use for: complex multi-file changes, security audits, root cause analysis, backend architecture
```
/OMG:escalate codex "
Task: [specific implementation task]
Context: [file paths, patterns to follow]
Verify: [how to confirm correctness]
"
```

### Mandatory Post-Plan Codex Validation
After any planning step inside CRAZY mode, run a Codex validation pass before implementation:

```bash
/OMG:escalate codex "Validate this plan for gaps, ordering risks, hidden edge cases, and missing verification. Return only actionable corrections."
```

### Gemini — UI/UX + Visual Design
**Gemini=UI/UX: frontend, visual, accessibility, responsive design, CSS, component styling**
Use for: frontend components, styling, visual review, accessibility, responsive layouts
```
/OMG:escalate gemini "
Task: [UI/design task]
Context: [component paths, design system]
"
```

## Phase 3: Anti-Hallucination Protocol

After EVERY implementation step:
1. **Run it** — show build/test output with exit code
2. **Never claim "looks correct"** — evidence or it didn't happen
3. **Never edit tests to match bugs** — fix the SOURCE code
4. **Never change only configs/scripts** — verify source files changed

## Phase 4: Error Loop Prevention

```
IF same_error >= 3:
    STOP. Do not retry.
    OPTIONS:
    1. /OMG:escalate codex "debug: [error] in [file]"
    2. Completely different approach
    3. Ask user for guidance
    NEVER retry the same thing a 4th time.
```

## Phase 5: Completion Gate

Don't stop until ALL verified:
- [ ] Changes compile/build (exit 0)
- [ ] Tests pass (exit 0)
- [ ] Security check on auth/payment/database code
- [ ] No TODO/FIXME left in new code
- [ ] Diff is surgical (minimal, no unnecessary changes)

## Phase 6: Report
```
CRAZY Mode — Complete
━━━━━━━━━━━━━━━━━━━━
Intent: [what was requested]
Result: [what was delivered]
Claude: [orchestration decisions]
Codex: [deep work done]
Gemini: [visual work done]
Verified: [build ✅ | test ✅ | lint ✅]
Files: [N files, M lines changed]
```
