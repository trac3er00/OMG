# Context: OAL v5 Hardening

## Rationale
OAL's security hooks currently fail-open on crash (exit 0 = allow). This means ANY Python exception in the firewall or secret-guard silently disables the security layer. Combined with logic defects (undefined variables, race conditions), the safety guarantees are weaker than they appear.

## Hook Overhead Analysis (current)

| Tool Call | PreToolUse | PostToolUse | Total Processes |
|-----------|------------|-------------|-----------------|
| Read      | secret-guard | tool-ledger | **2** |
| Bash      | firewall | tool-ledger + circuit-breaker | **3** |
| Write/Edit | secret-guard | tool-ledger + circuit-breaker + post-write + shadow_manager | **5** |

## Hook Overhead (after optimization)

| Tool Call | PreToolUse | PostToolUse | Total Processes | Saved |
|-----------|------------|-------------|-----------------|-------|
| Read      | secret-guard | *(none)* | **1** | -1 |
| Bash      | firewall | tool-ledger + circuit-breaker | **3** | 0 |
| Write/Edit | secret-guard | tool-ledger + post-write + shadow_manager* | **3-4** | -1 to -2 |

*shadow_manager skips early if no .oal/policy.yaml

## Key Gotchas

### 1. Hook crash isolation
Claude Code runs hooks as subprocesses. If a hook exits non-zero, it causes "Sibling tool call errored" for ALL hooks in the same event. This is why every hook uses exit(0). The fail-closed change must emit a DENY decision via JSON stdout BEFORE exiting 0 — not by changing the exit code.

### 2. PreToolUse vs Stop output schemas
- PreToolUse hooks: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`
- Stop hooks: `{"decision": "block", "reason": "..."}`
These are DIFFERENT schemas. Don't mix them.

### 3. settings.json matcher syntax
Matchers use pipe-separated tool names: `"Bash|Write|Edit|MultiEdit"`. Changing these affects which hooks fire. Test carefully.

### 4. fcntl availability
`fcntl` is Unix-only. The fallback (lockless write) is intentional for portability, but creates a race window. Acceptable trade-off for a local-only tool.

### 5. _common.py import safety
If we create hooks/_common.py and it has a syntax error, ALL hooks that import it will crash. Each hook MUST have an inline fallback:
```python
try:
    from _common import safe_main, deny_output
except Exception:
    # Inline fallback — hook still works if _common.py is broken
    def safe_main(fn): ...
    def deny_output(reason): ...
```

## Integration Points
- `state_migration.py` — imported by most hooks, already stable
- `policy_engine.py` — imported by firewall + secret-guard only
- `trust_review.py` — imported by config-guard only
- `shadow_manager.py` — imported by stop-gate + standalone PostToolUse

## Tech Debt Notes
- The trust manifest "signature" is a self-hash (not cryptographic verification). Noted but out of scope — fixing this requires an external signing mechanism.
- The control plane server has no auth. Deprioritized per user direction.
- Regex firewall bypass is inherent limitation — OAL is defense-in-depth, not sole defense.
