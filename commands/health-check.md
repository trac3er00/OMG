---
description: Verify project setup, context health, and tool integration
allowed-tools: Bash(ls:*), Bash(cat:*), Bash(find:*), Bash(grep:*), Bash(git:*), Bash(which:*), Bash(head:*), Bash(wc:*), Bash(stat:*), Bash(npm run:*), Bash(npx:*), Bash(pnpm run:*), Bash(yarn run:*), Bash(pytest:*), Bash(python3:*), Read, Grep, Glob
---

# /OMG:health-check

Run all checks silently, report only issues:

1. **Profile**: .omg/state/profile.yaml exists and has required fields (name, language, framework)?
   - FAIL if missing. WARN if key fields empty.

2. **Knowledge**: .omg/knowledge/ has content? Any decision files older than 30 days?
   - WARN if empty. WARN if stale files (suggest review).

3. **Quality Gate**: .omg/state/quality-gate.json exists and configured commands are runnable?
   - Check each command with `which` or `--version` where possible.
   - If execution is restricted, report WARN (not FAIL) with "cannot verify — restricted permissions".
   - If command found but fails: report FAIL with exit code.

4. **Secrets**: No .env committed to git? No API keys in tracked files?
   - `git ls-files | grep -i '\.env'` (exclude .env.example/.sample/.template).
   - FAIL if real .env files tracked.

5. **Tools**: Hooks installed? OMG team aliases available? MCP servers listed?
   - Check ~/.claude/hooks/.omg-version exists.
   - Check if `~/.claude/commands/OMG:teams.md` and `OMG:ccg.md` exist (WARN if missing, not FAIL).
   - List MCP servers from .mcp.json (informational).

6. **Failures**: Stale failure patterns in failure-tracker.json?
   - WARN if any pattern older than 24h. Suggest `/OMG:handoff` or manual reset.

7. **Context Size**: Estimate total injection from session-start + prompt-enhancer.
   - Sum: profile.yaml lines + working-memory.md lines + handoff.md lines.
   - WARN if >80 lines total.

**Report format:**
```
PASS [N] | WARN [N] | FAIL [N]

  FAIL profile: .omg/state/profile.yaml not found → run /OMG:init
  WARN quality: prettier not found → install or remove from quality-gate.json
  PASS secrets: no .env files tracked
  ...
```
