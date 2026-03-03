---
description: "Analyze uncommitted git changes and propose logical atomic commits grouped by concern."
allowed-tools: Read, Bash(python*:*), Grep, Glob
argument-hint: "[optional: working directory path]"
---

# /OMG:ai-commit — AI Commit Splitter

Analyze uncommitted git changes and propose logical atomic commits grouped by concern.

## Usage

```
/OMG:ai-commit
```

## What It Does

1. Reads hunk-level git diffs via `git_hunk()` from `tools/git_inspector.py`
2. Groups hunks by file type/category (python, javascript, config, docs, tests, etc.)
3. Separates test files from source code automatically
4. Generates conventional commit messages: `{type}({scope}): {description}`
5. Displays a human-readable preview of proposed commits

## Feature Flag

- **Flag name**: `OMG_AI_COMMIT_ENABLED`
- **Default**: `False` (disabled)
- **Enable**: `export OMG_AI_COMMIT_ENABLED=1`

Or set in `settings.json`:

```json
{
  "_omg": {
    "features": {
      "ai_commit": true
    }
  }
}
```

## Output Example

```
============================================================
  OMG AI Commit Splitter — Proposed Commit Plan
============================================================

  Total proposed commits: 3

  Commit 1: feat(tools): update commit_splitter.py
  ──────────────────────────────────────────────────
    • tools/commit_splitter.py
    (2 hunks)

  Commit 2: test(tests): update 2 test files
  ──────────────────────────────────────────────────
    • tests/tools/test_commit_splitter.py
    • tests/tools/test_git_inspector.py
    (4 hunks)

  Commit 3: docs(commands): update ai-commit.md
  ──────────────────────────────────────────────────
    • commands/ai-commit.md
    (1 hunk)

============================================================
  NOTE: This is a preview only. No commits were made.
============================================================
```

## Commit Type Mapping

| Category   | Default Type | Description              |
|------------|-------------|--------------------------|
| python     | `feat`      | Python source files      |
| javascript | `feat`      | JS/TS source files       |
| tests      | `test`      | Test files (any language) |
| docs       | `docs`      | Documentation files      |
| config     | `chore`     | Configuration files      |
| shell      | `chore`     | Shell scripts            |
| styles     | `style`     | CSS/SCSS/LESS files      |
| markup     | `feat`      | HTML/XML/SVG files       |
| other      | `chore`     | Unclassified files       |

## CLI Usage

```bash
# Preview commit plan from terminal
python3 tools/commit_splitter.py --dry-run
```

## Safety

- **Read-only**: Never executes `git commit` or modifies the working tree
- **Feature-gated**: Returns empty results when disabled
- **Non-destructive**: Safe to run at any time

## API

```python
from tools.commit_splitter import analyze_changes, generate_commit_plan, preview_commit_plan

# Get grouped hunks
groups = analyze_changes(cwd=".")

# Get full commit plan with messages
plan = generate_commit_plan(cwd=".")

# Get human-readable preview string
preview = preview_commit_plan(cwd=".")
```
