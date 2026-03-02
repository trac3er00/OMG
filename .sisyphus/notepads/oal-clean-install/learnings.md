# Learnings — oal-clean-install

## 2026-02-28 Session 2 (ses_35d76f9acffenr5Pim4tChFrCe)

### Current State (verified)
- Tasks 1-9 completed (evidence files exist)
- Task F2 completed (final snapshot evidence exists)
- Task 10 NOT done (no evidence file)
- Task F1 NOT done (no evidence file)

### Remaining .bak Issue
- Task 9 Check 3 FAILED: found 5 .bak files
- Root cause: installer creates `settings.json.bak.<timestamp>` during Step 6 (settings merge)
- Task 8 cleaned the OLD backup (20260227_222849) but then another installer run created a NEW one (20260227_223713)
- Confirmed: only 1 .bak file remains: `~/.claude/settings.json.bak.20260227_223713`
- `~/.claude/backups/` contains `.claude.json.backup.*` which are Claude Code INTERNAL — DO NOT TOUCH

### Critical Guardrails
- `~/.claude/backups/` = Claude Code internal, NEVER touch
- `~/.claude/.session-stats.json`, `cache/`, `history.jsonl`, `plugins/`, `projects/`, `skills/` = protected
- Only `settings.json.bak.*` at ~/.claude root level is safe to delete

### Installer Behavior
- `OAL-setup.sh reinstall` ALWAYS creates `settings.json.bak.<timestamp>` during settings merge
- This backup is created even with `--non-interactive --merge-policy=apply`
- Must be cleaned AFTER each installer run

### Hook Count
- 18 .py files in ~/.claude/hooks/ (including _common.py, quality-gate.py custom)
- All 18 verified present by Task 3 evidence
