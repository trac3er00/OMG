---
description: "Plan-driven implementation — reads active checklist and executes phase by phase."
allowed-tools: Read, Write, Edit, MultiEdit, Bash, Grep, Glob
argument-hint: "[--plan <path>] [--phase <N>] [--session this|fresh]"
---

# /OMG:start-work — Plan-Driven Implementation

Reads the active plan checklist and executes it item by item, phase by phase.

## Usage

```
/OMG:start-work                          # Resume from first unchecked item
/OMG:start-work --phase 3               # Start at Phase 3
/OMG:start-work --plan .omg/plans/abc/  # Use specific plan
/OMG:start-work --session fresh          # Hand off to fresh session
```

## How It Works

1. **Read checklist**: Find `.omg/state/_checklist.md` or specified plan
2. **Find current task**: First unchecked `- [ ]` item
3. **Execute**: Read → implement → verify → mark `[x]` → next
4. **Phase boundaries**: Complete all items in Phase N before moving to Phase N+1
5. **Branch awareness**: Create phase branch if missing, remind to merge after phase

## Implementation Mode

When start-work is active, the AI focuses exclusively on the plan:
- No tangent features or unrelated refactoring
- Each item follows: understand → implement → test → verify → checkmark
- Circuit breaker: 2x failure → escalate or ask user

## Progress

```
[Phase 3] ██████░░░░ 60% (3/5)
Current: N4.3 — Progress indicators in OMG-setup.sh
```

## Session Strategy

At startup, evaluates context usage:
- **<30% context used** → "Start in this session" (recommended)
- **30-50% context used** → User chooses
- **>50% context used** → "Start fresh session" (recommended)

### Fresh Session Handoff

Writes `.omg/state/handoff.md` with:
- Plan path and current phase
- First unchecked item
- Branch name
- Summary of completed work

### Current Session Mode

Compresses planning context, offloads to handoff file, begins Phase 1.

## Pause/Resume

- Run `/OMG:start-work` again to resume from first unchecked item
- State is persisted in the checklist itself (checked items = done)
- No separate tracking file needed

## Stuck Detection

After 2 failed attempts on the same item:
1. Circuit breaker triggers
2. Options: different approach, `/OMG:escalate`, or ask user
3. Never retry the same approach a 3rd time

## Deep-Plan Bridge

After `/OMG:deep-plan` completes and user selects "Start implementing":
- Automatically invokes `/OMG:start-work` with the generated plan
- Session strategy question is presented first
