---
description: Deep code review — reads file completely, checks line-by-line for issues, then analyzes whole-file structure. Enforces code hygiene.
allowed-tools: Read, Bash(cat:*), Bash(grep:*), Bash(wc:*), Bash(head:*), Bash(find:*), Bash(rg:*), Grep, Glob
argument-hint: "[file path or 'recent' for git-changed files]"
---

# /OMG:code-review — Line-by-Line + Structural Review

## Philosophy
Two passes: LINE-BY-LINE precision, then WHOLE-FILE understanding.
Don't just scan — READ and UNDERSTAND every line.

## Step 1: Determine Scope

- If file specified: review that file
- If "recent" or no argument: review uncommitted changes
  ```bash
  git diff --name-only HEAD 2>/dev/null
  git diff --cached --name-only 2>/dev/null
  ```

## Step 2: Read the FULL File First

Read the ENTIRE file. Not just the changed part. Not just a function.
Understanding comes from seeing the whole context.

Note:
- What does this file DO? (its purpose in the system)
- What are its DEPENDENCIES? (imports, calls)
- What does it EXPORT? (public API)

## Step 3: Line-by-Line Scan

For each line, check:

**Correctness:**
- Logic errors (off-by-one, null checks, type mismatches)
- Missing error handling (unhandled promises, bare except, no null check)
- Race conditions (shared state, async without await, unchecked concurrent access)

**Security (if auth/payment/database):**
- Hardcoded secrets → CRITICAL
- SQL injection (string concatenation in queries) → CRITICAL
- XSS (innerHTML, dangerouslySetInnerHTML) → HIGH
- Missing input validation → MEDIUM
- Overly permissive CORS/cookies → MEDIUM

**Hygiene:**
- Dead code (unused imports, variables, unreachable branches)
- Noise comments ("increment i", "return result", "constructor")
- console.log/print left in production code
- TODO/FIXME/HACK without tracking
- Overly complex functions (>40 lines → suggest extract)
- Duplicated logic (same pattern in 2+ places → suggest DRY)

## Step 4: Whole-File Structure Analysis

After line-by-line:
- Does the file do ONE thing well, or is it a dumping ground?
- Are functions ordered logically? (public first, helpers after, or lifecycle order)
- Is naming consistent? (camelCase throughout? PascalCase for classes?)
- Does it follow the project's domain pattern? (check .omg/knowledge/domain-patterns/)
- Any circular dependencies?
- Is error handling consistent across all functions?

## Step 5: Report

```
Code Review — [file]
━━━━━━━━━━━━━━━━━━━━

Structure: [CLEAN | NEEDS_WORK | MESSY]
Security:  [SAFE | REVIEW_NEEDED | CRITICAL]
Hygiene:   [CLEAN | NEEDS_CLEANUP]

Issues:
  [line:col] CRITICAL: [description]
  [line:col] HIGH: [description]
  [line:col] MEDIUM: [description]
  [line:col] LOW: [description]

Dead Code:
  [line] unused import: [name]
  [line] unreachable after return

Noise Comments (remove these):
  [line] "// increment counter"
  [line] "// return the value"

Structural:
  - [function] is [N] lines — consider extracting [suggestion]
  - [pattern] duplicated at lines [X] and [Y]

Recommendation: [summary of what to fix, in priority order]
```

## Step 6: For Security-Critical Files

If the file touches auth, payment, or database:
```
/OMG:escalate codex "Line-by-line security review of [file]. Check:
1. Every input validation point
2. Every database query for injection
3. Every auth check for bypass
4. Every secret reference for hardcoding
Report: line numbers + severity + fix suggestion"
```

## Anti-patterns
- DON'T skim and say "looks good" — read every line
- DON'T only check the diff — read the full file for context
- DON'T ignore test files — they can have real issues too
- DON'T add more noise comments as "fixes" — remove them instead
- DON'T suggest unnecessary code as improvements
