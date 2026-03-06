---
description: "Split staged work into coherent commits with the Bun commit tools."
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(bun:*)
argument-hint: "[--dry-run] [optional scope]"
---

# /OMG:ai-commit

Use this command when staged work needs to be grouped into reviewable commits before release.

## Tooling

- inspect hunks with `tools/git_inspector.ts`
- draft commit groupings with `tools/commit_splitter.ts`

## Example

```bash
bun tools/commit_splitter.ts --dry-run
```

Expected outcome:

- coherent commit groups
- a short message per group
- no unrelated files mixed into the same commit
