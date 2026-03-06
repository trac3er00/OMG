---
description: "Initialize project metadata for OMG on a Bun-first repository."
allowed-tools: Read, Write, Edit, Grep, Glob, Bash(rg:*), Bash(find:*), Bash(bun:*), Bash(git:*)
argument-hint: "[optional project goal]"
---

# /OMG:init

Use this to sketch initial project metadata and likely verification commands.

## Suggested defaults

```yaml
project:
  goal: "[describe the product or migration target]"
  test_cmd: "[detect: bun test/npm test/cargo test]"
  typecheck_cmd: "[detect: bunx tsc --noEmit or equivalent]"
  build_cmd: "[detect: bun run build or null]"
```

## Useful inventory command

```bash
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
  | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -10
```
