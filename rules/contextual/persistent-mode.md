# Persistent Work Mode (ulw / ralph)

**When:** User says "ulw", "ultrawork", "ralph", "끝까지", "don't stop", "keep going", "until done", "finish everything"

**Behavior:**
- Do NOT stop after one subtask. Work through the ENTIRE task list.
- If a checklist exists (.oal/state/_checklist.md), complete ALL items.
- If blocked on one item, SKIP it (mark [!]) and continue to the next.
- Return to skipped items after completing others.
- Use /OAL:escalate codex for complex code tasks in parallel.
- Use /OAL:escalate gemini for UI/visual tasks.
- Verify each completed item before moving on (run tests, show output).

**Completion:**
Only stop when:
1. All checklist items are [x] or [!] (with explanation for skipped)
2. All tests pass
3. Build succeeds
4. A completion summary is provided

**Anti-patterns:**
- Don't stop after just one fix and ask "anything else?"
- Don't skip verification to go faster
- Don't modify test expectations instead of fixing source code
