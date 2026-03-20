#!/usr/bin/env python3
"""
PostToolUse Hook: Circuit Breaker + Auto-Escalation (v4)
Key v4 change: After 3 failures, automatically SUGGESTS Codex/Gemini escalation
instead of just saying "stop". Actionable, not just blocking.
"""
import json, sys, os
from datetime import datetime, timezone, timedelta

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, _resolve_project_dir, is_stop_block_loop
from state_migration import resolve_state_dir

setup_crash_handler("circuit-breaker", fail_closed=False)

# Domain-aware routing hints: pattern prefix → suggested model
DOMAIN_MODEL_HINTS = {
    'Bash:pytest': 'codex',
    'Bash:npm': 'codex',
    'Bash:python': 'codex',
    'Write:': 'codex',
    'Edit:': 'codex',
}


def _get_domain_hint(pk: str) -> str:
    """Return model hint for a pattern key, or empty string."""
    for prefix, model in DOMAIN_MODEL_HINTS.items():
        if pk.startswith(prefix):
            return model
    return ''

data = json_input()

tool = data.get("tool_name", "")
tool_input = data.get("tool_input", {})
tool_response = data.get("tool_response", {})
project_dir = _resolve_project_dir()

ledger_dir = resolve_state_dir(project_dir, "state/ledger", "ledger")
tracker_path = os.path.join(ledger_dir, "failure-tracker.json")
os.makedirs(os.path.dirname(tracker_path), exist_ok=True)

# Determine failure
is_failure = False
if tool == "Bash":
    ec = None
    if isinstance(tool_response, dict):
        ec = tool_response.get("exitCode", tool_response.get("exit_code"))
    if ec is not None and ec != 0:
        is_failure = True
elif tool in ("Write", "Edit", "MultiEdit"):
    if isinstance(tool_response, dict) and not tool_response.get("success", True):
        is_failure = True

# Pattern key — normalized to prevent duplicates
# "npm test" and "npm run test" should be the same failure pattern
pattern_key = tool
if tool == "Bash":
    cmd = tool_input.get("command", "").strip()
    # Normalize: strip common prefixes, reduce to base command
    cmd_clean = cmd
    # Strip package manager prefixes: npx, pnpm, yarn, bunx
    cmd_clean = cmd_clean.replace("npx ", "").replace("pnpm ", "npm ").replace("yarn ", "npm ").replace("bunx ", "")
    # Strip python -m X → X (e.g., "python3 -m pytest" → "pytest")
    if cmd_clean.startswith("python3 -m "):
        cmd_clean = cmd_clean.replace("python3 -m ", "", 1)
    elif cmd_clean.startswith("python -m "):
        cmd_clean = cmd_clean.replace("python -m ", "", 1)
    words = cmd_clean.split()[:3]  # first 3 words for more specificity
    # Remove common noise: run, exec, --
    words = [w for w in words if not w.startswith("-") and w not in ("run", "exec")][:2]
    pattern_key = f"Bash:{' '.join(words)}" if words else f"Bash:{cmd[:30]}"
elif tool in ("Write", "Edit", "MultiEdit"):
    fp = tool_input.get("file_path", "")
    # Normalize: use basename to avoid path-length variants
    pattern_key = f"{tool}:{os.path.basename(fp)}" if fp else tool
pattern_key = pattern_key[:120].replace("\n", " ")

# Load tracker
tracker = {}
if os.path.exists(tracker_path):
    try:
        with open(tracker_path, "r") as f:
            tracker = json.load(f)
        if not isinstance(tracker, dict):
            tracker = {}
    except Exception:
        tracker = {}

# Evict stale (24h) + cap 100
now = datetime.now(timezone.utc)
cutoff = now - timedelta(hours=24)


def _parse_ts(ts_str):
    """Parse ISO timestamp string to datetime, returning None on failure."""
    try:
        # Handle both Z-suffix and +00:00 formats
        ts = ts_str.replace("Z", "+00:00") if ts_str.endswith("Z") else ts_str
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError, AttributeError):
        return None


def _effective_count(entry: dict[str, object], now: datetime) -> float:
    """Apply time-decay: failures >30 min old count as 0.5x."""
    last_failure = entry.get('last_failure', '')
    last_ts = _parse_ts(last_failure if isinstance(last_failure, str) else '')
    raw_count = entry.get('count', 0)
    count_value = float(raw_count) if isinstance(raw_count, (int, float)) else 0.0
    if last_ts is None:
        return count_value
    age_minutes = (now - last_ts).total_seconds() / 60
    if age_minutes > 30:
        return count_value * 0.5
    return count_value


tracker = {k: v for k, v in tracker.items()
           if isinstance(v, dict) and (_parse_ts(v.get("last_failure", "")) or cutoff) >= cutoff}
if len(tracker) > 100:
    for k in sorted(tracker, key=lambda x: tracker[x].get("last_failure", ""))[:-100]:
        del tracker[k]

if is_failure:
    entry_raw = tracker.get(pattern_key, {"count": 0, "errors": []})
    if not isinstance(entry_raw, dict):
        entry_raw = {"count": 0, "errors": []}
    entry: dict[str, object] = dict(entry_raw)
    entry_count = entry.get("count", 0)
    count_value = entry_count if isinstance(entry_count, (int, float)) else 0
    entry["count"] = count_value + 1
    entry["last_failure"] = now.isoformat()

    err = ""
    if isinstance(tool_response, dict):
        err = str(tool_response.get("stderr", tool_response.get("stdout", "")))[:200].strip()
    errors = entry.get("errors", [])
    if not isinstance(errors, list):
        errors = []
    # Deduplicate: don't store the same error message twice in a row
    if err and (not errors or errors[-1] != err):
        errors.append(err)
    entry["errors"] = errors[-3:]  # keep last 3 unique errors
    tracker[pattern_key] = entry

    try:
        import fcntl
        # Open read+write without truncating, acquire lock, THEN truncate and write.
        # This prevents data loss if lock acquisition fails after truncation.
        fd = open(tracker_path, "a+")
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.seek(0)
        fd.truncate()
        json.dump(tracker, fd, indent=2)
        fd.flush()
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()
    except (ImportError, BlockingIOError):
        # Fallback: write without lock (better than losing data)
        try:
            with open(tracker_path, "w") as f:
                json.dump(tracker, f, indent=2)
        except Exception:
            pass
    except Exception:
        pass

    count = entry["count"]
    effective_count = _effective_count(entry, now)
    domain_hint = _get_domain_hint(pattern_key)
    recent_errs = "\n".join(f"  - {e}" for e in entry["errors"] if e)

    if effective_count >= 5:
        last_err = entry['errors'][-1][:80] if entry['errors'] else 'unknown'
        options_json = json.dumps({
            "question": f"'{pattern_key}' failed {count}x. This approach is broken. How to proceed?",
            "header": "Escalate",
            "options": [
                {"label": "Escalate to Codex", "description": f"Debug: {pattern_key} fails with {last_err}"},
                {"label": "Escalate to Gemini", "description": f"Review: approach for {pattern_key}"},
                {"label": "Different approach", "description": "Ask user for a completely different strategy"},
                {"label": "Skip this step", "description": "Mark [!] in checklist and move on"}
            ]
        })
        print(
            f"CIRCUIT BREAKER: '{pattern_key}' failed {count}x (effective {effective_count:.1f}x).\n"
            f"STOP. This approach is broken.\n"
            f"{recent_errs}\n\n"
            f"Domain hint: {domain_hint or 'none'}\n"
            f"@@ASK_USER_OPTIONS@@\n{options_json}",
            file=sys.stderr
        )
        # NOTE: exit(0), not exit(2). Non-zero exits crash sibling hooks
        # ("Sibling tool call errored"). The warning is in stderr.
        sys.exit(0)

    elif effective_count >= 3:
        # Break cycle: if stop hooks are already looping, skip this warning
        if is_stop_block_loop():
            sys.exit(0)
        last_err = entry['errors'][-1][:150] if entry['errors'] else 'unknown'
        options_json = json.dumps({
            "question": f"'{pattern_key}' failed {count}x. Stop auto-retrying. What next?",
            "header": "Stuck",
            "options": [
                {"label": "Different approach", "description": "Try a fundamentally different strategy"},
                {"label": "Escalate to Codex", "description": f"Ask: Why does {pattern_key} keep failing?"},
                {"label": "Ask user", "description": "Get user guidance on how to proceed"}
            ]
        })
        print(
            f"CIRCUIT BREAKER WARNING: '{pattern_key}' failed {count}x (effective {effective_count:.1f}x).\n"
            f"Last error: {last_err}\n\n"
            f"Domain hint: {domain_hint or 'none'}\n"
            f"@@ASK_USER_OPTIONS@@\n{options_json}",
            file=sys.stderr
        )
        sys.exit(0)

else:
    # On success, clear this pattern AND similar variants
    # Helper to normalize a tracker key by re-normalizing the command part
    def _normalize_tracker_key(pk):
        """Normalize a tracker key by applying the same rules as pattern_key generation."""
        if not pk.startswith("Bash:"):
            return pk
        
        cmd = pk[5:]  # Remove "Bash:" prefix
        # Apply the same normalization as in pattern_key generation
        cmd_clean = cmd
        cmd_clean = cmd_clean.replace("npx ", "").replace("pnpm ", "npm ").replace("yarn ", "npm ").replace("bunx ", "")
        if cmd_clean.startswith("python3 -m "):
            cmd_clean = cmd_clean.replace("python3 -m ", "", 1)
        elif cmd_clean.startswith("python -m "):
            cmd_clean = cmd_clean.replace("python -m ", "", 1)
        words = cmd_clean.split()[:3]
        words = [w for w in words if not w.startswith("-") and w not in ("run", "exec")][:2]
        normalized_cmd = ' '.join(words) if words else cmd[:30]
        return f"Bash:{normalized_cmd}"
    
    normalized_pattern_key = _normalize_tracker_key(pattern_key)
    changed = False
    keys_to_remove = []
    
    for k in tracker:
        # Normalize both keys for comparison
        normalized_k = _normalize_tracker_key(k)
        if normalized_k == normalized_pattern_key:
            keys_to_remove.append(k)
    
    for k in keys_to_remove:
        del tracker[k]
        changed = True
    
    if changed:
        try:
            with open(tracker_path, "w") as f:
                json.dump(tracker, f, indent=2)
        except Exception:
            pass
        _recovery_path = os.path.join(ledger_dir, 'recovery.jsonl')
        try:
            import json as _json
            _rec = _json.dumps({
                'pattern': pattern_key,
                'recovered_at': now.isoformat(),
                'cleared_count': len(keys_to_remove),
            })
            with open(_recovery_path, 'a') as _rf:
                _rf.write(_rec + '\n')
            try:
                with open(_recovery_path, 'r') as _rf:
                    _lines = _rf.readlines()
                if len(_lines) > 200:
                    with open(_recovery_path, 'w') as _rf:
                        _rf.writelines(_lines[-200:])
            except OSError:
                pass
        except Exception:
            pass

sys.exit(0)
