---
description: Verify project setup, context health, and tool integration
allowed-tools: Bash(ls:*), Bash(cat:*), Bash(find:*), Bash(grep:*), Bash(git:*), Bash(which:*), Bash(head:*), Bash(wc:*), Bash(stat:*), Bash(npm run:*), Bash(npx:*), Bash(pnpm run:*), Bash(yarn run:*), Bash(pytest:*), Bash(python3:*), Read, Grep, Glob
---

# /OAL:health-check

Run all checks silently, report only issues:

1. **Profile**: .oal/state/profile.yaml exists and has required fields (name, language, framework)?
   - FAIL if missing. WARN if key fields empty.

2. **Knowledge**: .oal/knowledge/ has content? Any decision files older than 30 days?
   - WARN if empty. WARN if stale files (suggest review).

3. **Quality Gate**: .oal/state/quality-gate.json exists and configured commands are runnable?
   - Check each command with `which` or `--version` where possible.
   - If execution is restricted, report WARN (not FAIL) with "cannot verify — restricted permissions".
   - If command found but fails: report FAIL with exit code.

4. **Secrets**: No .env committed to git? No API keys in tracked files?
   - `git ls-files | grep -i '\.env'` (exclude .env.example/.sample/.template).
   - FAIL if real .env files tracked.

5. **Tools**: Hooks installed? OAL team aliases available? MCP servers listed?
   - Check ~/.claude/hooks/.oal-version exists.
   - Check if `~/.claude/commands/OAL:teams.md` and `OAL:ccg.md` exist (WARN if missing, not FAIL).
   - List MCP servers from .mcp.json (informational).

6. **Failures**: Stale failure patterns in failure-tracker.json?
   - WARN if any pattern older than 24h. Suggest `/OAL:handoff` or manual reset.

7. **Context Size**: Estimate total injection from session-start + prompt-enhancer.
   - Sum: profile.yaml lines + working-memory.md lines + handoff.md lines.
   - WARN if >80 lines total.

**Report format:**
```
PASS [N] | WARN [N] | FAIL [N]

  FAIL profile: .oal/state/profile.yaml not found → run /OAL:init
  WARN quality: prettier not found → install or remove from quality-gate.json
  PASS secrets: no .env files tracked
  ...
```
