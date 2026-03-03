# OMG Remediation — Learnings

## [2026-03-01] Session Start: ses_358e02746ffe6QlOdpElv2OUmt

### Key Codebase Facts

- **NOT a git repo** — `git diff` / `git worktree` unavailable. Use file snapshots or direct grep for verification.
- `hooks/_common.py` already has `get_project_dir()` at line ~17 that does the raw `os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())`. T1 must ADD a NEW `_resolve_project_dir()` function that validates `.omg/` existence, distinct from the existing function.
- `hooks/_common.py` top-level import: `from datetime import datetime, timezone` — `timezone` is already available in _common.py scope.
- `hooks/post-write.py:29-30`: The "duplicate" comment is NOT identical — line 29 says `best-effort, non-blocking` and line 30 says `opt-in via quality-gate.json, non-blocking`. The old one (line 29) should be removed; line 30 is the updated description.
- `hooks/prompt-enhancer.py:174`: `from datetime import datetime as _dt` is a LOCAL import inside a function. Fix: change to `from datetime import datetime as _dt, timezone` and replace `_dt.utcnow().isoformat() + 'Z'` with `_dt.now(timezone.utc).isoformat()`.
- `hooks/_common.py:setup_crash_handler()` — DO NOT TOUCH. It's the crash isolation safety net for all 19 hooks.
- All hooks use `print(..., file=sys.stderr)` for logging — NEVER `logging.getLogger`.
- OMG is stdlib-only — NO external dependencies ever.
- Exit codes must stay 0 — crash isolation policy.

### Pattern: Import style in hooks
- Top-level imports: bare `import os`, `import sys`, `import json`
- Internal/local imports (inside functions): used sparingly for optional features

### Verification approach (no git)
- Use `python3 -m py_compile <file>` for syntax validation
- Use `grep` and `ast-grep` for pattern verification
- For "before/after" comparison: read file content before and after to compare

- 2026-02-28: In prompt signal matching, use word-boundary regex for Latin tokens (re.search with  + re.escape + IGNORECASE) and keep Hangul tokens as substring matching because Korean lacks reliable word boundaries. Also validate loaded .index.json cache type with isinstance(index, dict) and rebuild on mismatch.
- 2026-02-28: Correction note: represent regex boundary as literal \b in documentation text to avoid control-character insertion when appending notes.
