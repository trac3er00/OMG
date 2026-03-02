# Code Hygiene

**Always active.**

**No unnecessary code:**
- Don't add code "just in case" — every line must serve the current requirement
- Don't add empty catch blocks, unused imports, dead variables, or placeholder functions
- Don't copy boilerplate that isn't needed for this specific feature
- If removing code makes the program work the same → remove it

**No noise comments:**
- NEVER: `// increment i by 1`, `// return the result`, `// constructor`, `// import modules`
- NEVER: `// TODO: implement` (either implement it or note it in working-memory)
- OK: WHY comments (`// Retry 3x because Stripe webhook occasionally 504s`)
- OK: WARN comments (`// SECURITY: raw SQL here because ORM can't express this join`)
- OK: API contract comments (`// @param userId - must be UUID v4, not email`)

**Line-by-line awareness:**
- Before editing a file: read the FULL file (or relevant section), not just the target function
- After editing: re-read to verify no duplicate imports, no orphaned variables, no broken references
- Check: does this change break anything ABOVE or BELOW the edit?

**Before claiming completion, verify:**
- `grep -n "TODO\|FIXME\|HACK\|XXX"` — are any left unresolved?
- No console.log/print debugging statements left in production code
- No commented-out code blocks (delete or extract to a branch)
