---
description: Intelligent session transfer — captures WHAT was done, HOW it was done, and WHY decisions were made. Works across platforms (Claude Code → Claude.ai).
allowed-tools: Read, Write, Edit, MultiEdit, Bash(git:*), Bash(cat:*), Bash(wc:*), Bash(find:*), Bash(mkdir:*), Bash(tee:*), Grep, Glob
argument-hint: "[optional: --portable for cross-platform, or reason for handoff]"
---

# /OMG:handoff — Intelligent Session Transfer

## Size Budget (CRITICAL)
- handoff.md: **≤ 60 lines** (briefing, not data dump)
- handoff-portable.md: **≤ 100 lines** (fits most context windows)
- If a section grows too long, SUMMARIZE — don't truncate mid-sentence

## Philosophy
A handoff is NOT a data dump. It's a **briefing** for the next session.
The next Claude (in ANY platform) should read this and know EXACTLY:
1. What was the goal
2. What was accomplished (with evidence)
3. What decisions were made and WHY
4. What failed and WHY (so it doesn't repeat)
5. The single most important next action

## Step 1: Gather Intelligence

Read these (silently, don't dump to user):
- .omg/state/profile.yaml or project.md (project identity)
- .omg/state/working-memory.md or _plan.md + _checklist.md (task state)
- .omg/state/ledger/failure-tracker.json (what failed)
- .omg/state/ledger/tool-ledger.jsonl (last 20 entries for activity summary)
- git diff --stat + git log --oneline -5 (what changed)

## Step 2: Synthesize — Write .omg/state/handoff.md

DO NOT copy-paste raw data. SYNTHESIZE into this structure (≤ 60 lines total):

```markdown
# Handoff — [date]

## Goal
[1 sentence: what we're trying to achieve]

## What Was Done (with evidence)
- [action]: [result] (verified: [command, exit code])
Total: [N] files changed, [M] lines

## Key Decisions (preserve these)
- Chose [X] over [Y] because [reason]

## What Failed (don't repeat these)
- [Approach A]: failed because [root cause]

## Current State
Branch: [name] | Uncommitted: [N files]
Checklist: [done]/[total] steps

## Exact Next Step
[Single most important action with specific instructions]
Read [specific file] first, then [specific action]

## Files to Read on Resume
1. .omg/state/profile.yaml (project identity)
2. .omg/state/handoff.md (this file)
3. [specific file relevant to next step]
```

## Step 3: Generate Portable Version (≤ 100 lines)

ALWAYS also generate `.omg/state/handoff-portable.md` — a **self-contained** version that works
when pasted into Claude.ai, ChatGPT, or any AI chat without file access.

Portable version differences:
- **Include** project identity inline (language, framework, key conventions) — no file references
- **Include** the relevant code context (key interfaces, schemas, or config) — the next AI can't Read files
- **Replace** "Read file X" with actual excerpts of the critical parts
- **Total ≤ 100 lines** (fits in most context windows)

## Step 4: Write Files

**IMPORTANT: File write method — prevents "Error writing file".**

First ensure directory exists:
```
mkdir -p .omg/state
```

Then write with `Write` tool. **If Write fails** (file already exists), use Bash heredoc:
```bash
cat > .omg/state/handoff.md << 'HANDOFF_EOF'
[content here]
HANDOFF_EOF
```

Do the same for handoff-portable.md.

## Step 5: Present BOTH Versions

```
Handoff ready:
  📁 .omg/state/handoff.md ([N] lines) — for Claude Code sessions
  📋 .omg/state/handoff-portable.md ([N] lines) — for Claude.ai / other platforms

To continue in Claude Code:
  "Read .omg/state/profile.yaml and .omg/state/handoff.md, continue where I left off."

To continue in Claude.ai (copy-paste the portable version):
  [Show the user the full content of handoff-portable.md so they can copy it]
```

## Anti-patterns
- Don't dump raw file contents into handoff (synthesize)
- Don't list every tool call (summarize activity)
- Don't include full error output (root cause only)
- Don't make the portable version reference files it can't access
- Don't exceed 60 lines / 100 lines budget
- Don't use Write tool alone if the file already exists — fallback to Bash heredoc
