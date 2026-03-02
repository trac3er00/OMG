# Write/Edit Verification Rule

When any file write or edit operation shows an error, warning, or hook error:

1. **NEVER claim success** without reading the file to verify changes are present
2. **Hook errors from external plugins** (e.g. security_reminder_hook.py) are warnings — the write may have succeeded. READ the file to check.
3. **"Error editing file"** means the Edit tool failed. Use an alternative:
   - Try `Write` tool (creates new file)
   - Try Bash: `cat > path/to/file << 'EOF'\n[content]\nEOF`
   - Try Bash: `tee path/to/file << 'EOF'\n[content]\nEOF`
4. **"Error writing file"** (file already exists) — use `Edit` or Bash heredoc
5. After ANY retry, READ the file again to confirm

## Common Hook Error Pattern
```
Error: PreToolUse:Write hook error: [python3 .../security_reminder_hook.py]: ⚠️ Security Warning: ...
```
This means an external hook emitted a warning. The file write likely succeeded.
**Action:** Read the file to verify, then continue. Do NOT retry blindly.

## Anti-pattern: False Success
❌ "I've updated the file successfully" (without reading it)
✅ "Let me verify the changes were applied..." → [Read file] → "Confirmed, the changes are in place."
