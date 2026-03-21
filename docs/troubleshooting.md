# Troubleshooting

## Common Issues

### Hooks not firing

**Symptoms:** No OMG injections, no stop-gate blocks, no prompt enhancement.

**Fix:**
```bash
# Check hooks are installed
ls ~/.claude/hooks/*.py

# Verify settings.json has hook entries
grep -c "hooks" ~/.claude/settings.json

# Re-install hooks
./OMG-setup.sh reinstall
```

### Python version too old

**Symptoms:** `SyntaxError` in hooks, `fastmcp` import fails.

**Fix:**
```bash
python3 --version  # Need 3.10+
# macOS
brew install python@3.12
# Ubuntu/Debian
sudo apt install python3.12
# Or use pyenv
pyenv install 3.12.0 && pyenv global 3.12.0
```

### MCP server not starting

**Symptoms:** `omg-control not found in .mcp.json`

**Fix:**
```bash
# Check .mcp.json exists
cat .mcp.json | python3 -m json.tool

# Re-run setup to configure MCP
/OMG:init setup --preset balanced
```

### Stop hook loops

**Symptoms:** Repeated "Stop hook feedback" messages, can't complete tasks.

**Fix:**
```bash
# Reset the stop block tracker
rm .omg/state/ledger/.stop-block-tracker.json

# Or hand off to fresh session
/OMG:handoff
```

### Context overflow

**Symptoms:** Compaction happening frequently, losing context.

**Fix:**
```
# Hand off state to fresh session
/OMG:handoff

# Resume in new session from handoff file
# Claude will read .omg/state/handoff.md automatically
```

### Cost tracking not working

**Symptoms:** `/OMG:stats cost` shows nothing.

**Fix:**
```bash
# Enable the feature flag
export OMG_COST_TRACKING_ENABLED=1

# Or set in settings.json
# settings.json → _omg.features.COST_TRACKING: true
```

## OS-Specific Notes

### macOS

- Use Homebrew Python: `brew install python@3.12`
- File permissions: macOS may quarantine downloaded scripts — run `xattr -d com.apple.quarantine OMG-setup.sh`
- If `shasum` missing: `brew install coreutils`

### Linux (Ubuntu/Debian)

- Install venv: `sudo apt install python3-venv`
- If `python3` not found: `sudo apt install python3`
- Permissions: may need `chmod +x OMG-setup.sh`

### Linux (Fedora/RHEL)

- Install Python: `sudo dnf install python3`
- Install venv: `sudo dnf install python3-venv` (or built-in with dnf Python)

### Windows (WSL)

- OMG requires WSL2 with Ubuntu
- Install: `wsl --install -d Ubuntu`
- Then follow Linux instructions inside WSL

## Diagnostics

```bash
# Full system check
/OMG:validate

# Plugin conflicts
/OMG:validate plugins

# View hook error log
cat .omg/state/ledger/hook-errors.jsonl | tail -5 | python3 -m json.tool
```

## Getting Help

- Issues: https://github.com/trac3r00/OMG/issues
- Command reference: `/OMG:validate` for system status
