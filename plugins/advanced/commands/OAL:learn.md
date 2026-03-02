---
description: Create a reusable skill from a pattern you just did. Auto-detects repetitive work and offers to skill-ify it.
allowed-tools: Read, Write, Edit, MultiEdit, Bash(git:*), Bash(cat:*), Bash(find:*), Bash(ls:*), Bash(mkdir:*), Bash(tee:*), Grep, Glob
argument-hint: "[skill name] or 'auto' to detect from recent work"
---

# /OAL:learn — Auto-Skill Creator

## What This Does
Takes something you just did (test pattern, implementation approach, debugging method)
and turns it into a reusable Claude Code skill that activates automatically next time.

## Usage

### Manual: /OAL:learn [skill-name]
Claude asks you what the pattern is and creates a skill.

### Auto: /OAL:learn auto
Claude analyzes recent tool-ledger entries to detect repetitive patterns.

## Step 1: Detect Pattern

### If "auto":
Read .oal/state/ledger/tool-ledger.jsonl (last 50 entries).
Look for:
- Same file types being created repeatedly (e.g., always creating .test.ts with same structure)
- Same command sequences repeated (e.g., lint → typecheck → test → format)
- Same file reading patterns (e.g., always reading ARCHITECTURE_TOC.md before edits)
- Same error→fix sequences (e.g., import error → add import → retry)

Present findings: "I noticed you repeatedly [pattern]. Want me to make this a skill?"

### If manual:
Ask: "Describe the pattern you want to save. What triggers it? What should happen?"

## Step 2: Create Skill

Skills live in: ~/.config/oal/skills/ (personal) or .oal/skills/ (project)

```
~/.config/oal/skills/[skill-name]/
├── SKILL.md          # Instructions Claude follows
├── templates/        # Template files (optional)
└── scripts/          # Helper scripts (optional)
```

### SKILL.md Format:
```markdown
# [Skill Name]

## When to activate
[Trigger conditions — what keywords, file types, or situations activate this]

## Steps
1. [Step 1]
2. [Step 2]
...

## Templates
[If the skill creates files, include template content or reference templates/]

## Quality check
[How to verify the skill worked correctly]

## Examples
[1-2 examples of good output]
```

## Step 3: Register

Add skill to .oal/skills-index.json:
```json
{
  "skills": [
    {
      "name": "api-test-pattern",
      "trigger": ["test", "api", "endpoint"],
      "path": "~/.config/oal/skills/api-test-pattern/SKILL.md",
      "description": "Creates API endpoint tests with auth, validation, edge cases"
    }
  ]
}
```

## Step 4: Verify
- Create a test invocation
- Confirm the skill produces correct output
- Tell user: "Skill '[name]' saved. It'll activate when you [trigger condition]."

## Built-in Skill Candidates (suggest these)
When detecting patterns, especially look for:
- **Test patterns**: How tests are structured for this project
- **Component patterns**: How new React/Vue/etc components are created
- **API patterns**: How new endpoints are added (route + handler + validation + test)
- **Migration patterns**: How DB migrations are created and verified
- **PR patterns**: How PRs are structured (description, checklist, labels)
- **Debug patterns**: Project-specific debugging steps (log locations, common fixes)

## Aggregated Patterns (Auto)
When you run `/OAL:learn auto`, OAL reads all learning files from `.oal/state/learnings/` and generates `.oal/knowledge/critical-patterns.md` with your top tool and file patterns.

Run: `python3 -c "import sys; sys.path.insert(0,'hooks'); from _learnings import save_critical_patterns; save_critical_patterns('.')"`
## File Write Fallback
If `Write` fails (file exists), use `Edit` or Bash heredoc:
```bash
cat > path/to/skill.md << 'SKILLEOF'
[content]
SKILLEOF
```
Always READ the file after writing to verify changes.
