"""Shared utilities for OMG hooks. Pure stdlib — no external deps."""
import json
import os
import sys
import fcntl
from datetime import datetime, timezone

# --- Stop-Block Loop Breaker ---
_STOP_BLOCK_TRACKER = ".omg/state/ledger/.stop-block-tracker.json"
# Max seconds between blocks to consider it a loop
_BLOCK_LOOP_WINDOW_SECS = 30
# How many consecutive blocks before we skip
_BLOCK_LOOP_THRESHOLD = 2
# Block reasons that indicate a loop scenario (Guard 5 skip-eligible)
_LOOP_BLOCK_REASONS = {"planning_gate", "ralph_loop", "quality_check", "block_decision", "unknown"}

# --- Performance Budget Constants ---
PRE_TOOL_INJECT_MAX_MS = 100
STOP_CHECK_MAX_MS = 15000
STOP_DISPATCHER_TOTAL_MAX_MS = 90000

def json_input():
    """Parse JSON from stdin. Returns dict or exits 0 on parse failure."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)


def get_project_dir():
    """Get project directory from env or cwd."""
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _resolve_project_dir():
    """Get and validate project directory; warns if .omg/ missing."""
    path = get_project_dir()
    if not os.path.isdir(os.path.join(path, ".omg")):
        print(f"[OMG] Warning: .omg/ not found in {path}", file=sys.stderr)
    return path

def deny_decision(reason):
    """Emit a PreToolUse deny decision to stdout."""
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)


def block_decision(reason):
    """Emit a Stop hook block decision to stdout.

    Also records the block for loop detection. Every stop hook that calls
    block_decision() contributes to the loop breaker counter, so deadlocks
    are detected regardless of which specific hook triggers the block.
    """
    # Record block BEFORE emitting -- ensures tracker is updated even if
    # the process is killed after emitting the decision.
    try:
        record_stop_block()
    except Exception:
        pass  # never let tracker failure prevent the block decision
    json.dump({"decision": "block", "reason": reason}, sys.stdout)


def setup_crash_handler(hook_name, fail_closed=False):
    """Install a crash handler that prevents non-zero exits.

    fail_closed=True: emit deny on crash (for security hooks like firewall, secret-guard)
    fail_closed=False: silently exit 0 (for non-security hooks)
    """
    def _excepthook(exc_type, exc_val, exc_tb):
        print(f"OMG hook error ({hook_name}): {exc_val}", file=sys.stderr)
        log_hook_error(hook_name, exc_val)
        if fail_closed:
            try:
                deny_decision(f"OMG {hook_name} crash: {exc_val}. Denying for safety.")
            except Exception:
                pass
        os._exit(0)
    sys.excepthook = _excepthook


def read_file_safe(path, max_bytes=2000):
    """Read file content safely, returning None on any failure."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read(max_bytes).strip()
        return text or None
    except Exception:
        return None


def log_hook_error(hook_name, error, context=None):
    """Log hook error to .omg/state/ledger/hook-errors.jsonl with file locking.
    
    Args:
        hook_name: Name of the hook that errored
        error: Exception or error message
        context: Optional dict with additional context
    
    Silently fails if logging cannot be completed (crash isolation).
    """
    try:
        project_dir = get_project_dir()
        ledger_dir = os.path.join(project_dir, ".omg", "state", "ledger")
        os.makedirs(ledger_dir, exist_ok=True)
        
        ledger_path = os.path.join(ledger_dir, "hook-errors.jsonl")
        
        # Rotation: if file > 100KB, rename to .hook-errors.jsonl.1
        try:
            if os.path.exists(ledger_path):
                size = os.path.getsize(ledger_path)
                if size > 100 * 1024:  # 100KB
                    archive = ledger_path + ".1"
                    if os.path.exists(archive):
                        try:
                            os.remove(archive)
                        except OSError:
                            pass
                    try:
                        os.rename(ledger_path, archive)
                    except OSError:
                        pass
        except Exception:
            pass
        
        # Build entry
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "hook": hook_name,
            "error": str(error),
        }
        if context:
            entry["context"] = context
        
        # Write with file locking
        try:
            fd = open(ledger_path, "a")
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            fd.write(json.dumps(entry, separators=(",", ":")) + "\n")
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            fd.close()
        except (ImportError, BlockingIOError):
            # Fallback: write without locking
            try:
                with open(ledger_path, "a") as f:
                    f.write(json.dumps(entry, separators=(",", ":")) + "\n")
            except Exception as e:
                print(f"[OMG] _common.py: {type(e).__name__}: {e}", file=sys.stderr)
                pass
        except Exception as e:
            print(f"[OMG] _common.py: {type(e).__name__}: {e}", file=sys.stderr)
            pass
    except Exception as e:
        print(f"[OMG] _common.py: {type(e).__name__}: {e}", file=sys.stderr)
        pass


def atomic_json_write(path, data):
    """Atomically write JSON data to a file using temp + rename.
    
    Args:
        path: Target file path
        data: Data to write as JSON
    
    Creates parent directories if needed. Silently fails on error.
    """
    try:
        # Create parent dirs
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        
        # Write to temp file
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        
        # Atomic rename
        os.rename(tmp_path, path)
    except Exception as e:
        print(f"[OMG] _common.py: {type(e).__name__}: {e}", file=sys.stderr)
        pass


# Feature flags cache — read settings.json once per hook invocation
_FEATURE_CACHE = {}


def get_feature_flag(flag_name, default=True):
    """Get feature flag value with resolution order: env var → settings.json → default.
    
    Env var format: OMG_{FLAG_NAME.upper()}_ENABLED
    Values: "0"/"false"/"no" → False, "1"/"true"/"yes" → True
    
    Returns default on any error (missing settings.json, malformed JSON, etc).
    """
    # Check environment variable first
    env_key = f"OMG_{flag_name.upper()}_ENABLED"
    env_val = os.environ.get(env_key, "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    
    # Check settings.json (cached)
    if not _FEATURE_CACHE:
        try:
            settings_path = os.path.join(get_project_dir(), "settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    _FEATURE_CACHE.update(settings.get("_oal", {}).get("features", {}))
        except Exception:
            pass  # Return default on any error
    
    # Return from cache, or default
    return _FEATURE_CACHE.get(flag_name, default)


# Permission mode helpers
BYPASS_MODES = frozenset({"bypasspermissions", "dontask"})


def is_bypass_mode(data):
    """Return True if the hook input indicates permission prompts should be skipped.

    Claude Code passes ``permission_mode`` in the hook input.  When the user
    enables *bypass permissions* or *don't ask* mode, hooks should still
    enforce hard denials (critical safety) but must NOT emit ``ask`` decisions
    that would re-introduce confirmation prompts.
    """
    if not isinstance(data, dict):
        return False
    mode = (data.get("permission_mode") or "").lower().strip()
    return mode in BYPASS_MODES


# --- Subagent & Context-Limit Detection ---

# Stop hook feedback markers injected by Claude Code when a stop hook blocks
_STOP_HOOK_FEEDBACK_PREFIX = "Stop hook feedback:"


def should_skip_stop_hooks(data):
    """Return True if stop hooks should exit immediately without blocking.
    
    Detects four conditions:
    1. stop_hook_active flag (Claude Code's built-in re-entry guard)
    2. Stop hook feedback loop (previous block was already injected,
       agent couldn't respond — blocking again is futile)
    3. Context-limit / rate-limit stop (blocking these prevents compaction
       or creates infinite retry loops — must allow stop to proceed)
    4. File-based loop breaker (if hooks blocked >= 2 times within 90s,
       agent cannot resolve — likely context-limited)
    
    Safe for all stop hooks to call at the top of main().
    """
    if not isinstance(data, dict):
        return False

    # Guard 1: Claude Code's built-in re-entry prevention
    if data.get("stop_hook_active", False):
        return True

    # Guard 3: Context-limit and rate-limit stop detection
    #   When context is exhausted, Claude Code needs to stop so it can compact.
    #   Blocking these stops causes a deadlock: can't compact because can't stop,
    #   can't continue because context is full.
    #   Similarly, rate-limit stops (429/quota) must not be blocked or they loop.
    stop_reason = str(data.get("stop_reason", data.get("stopReason", ""))).lower()
    end_turn_reason = str(data.get("end_turn_reason", data.get("endTurnReason", ""))).lower()
    signal_text = " ".join(
        str(data.get(k, ""))
        for k in ("message", "error", "reason", "type", "event")
    ).lower()
    context_limit_markers = (
        "context window",
        "token limit",
        "too much context",
        "context length exceeded",
        "maximum context length",
        "prompt is too long",
        "request too large",
        "input too long",
        "context_limit",
        "context overflow",
    )
    if any(marker in signal_text for marker in context_limit_markers):
        print(
            "[OMG] Context limit detected: allowing stop so compaction can proceed. "
            "If this repeats, run /OMG:handoff and resume from .omg/state/handoff.md.",
            file=sys.stderr,
        )
        return True

    # Guard 2: Check transcript for stop-hook feedback loop
    #   If the last user message is stop hook feedback, the hooks already
    #   blocked once and the agent tried (and failed) to respond.
    #   Blocking again creates an unrecoverable loop.
    transcript_path = data.get("transcript_path", "")
    if transcript_path and os.path.exists(transcript_path):
        try:
            last_user_text = ""
            with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") == "user":
                        msg = entry.get("message", {})
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            last_user_text = content
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    last_user_text = block.get("text", "")
                                elif isinstance(block, str):
                                    last_user_text = block
            # If last user message is stop hook feedback, we're in a loop
            if last_user_text.startswith(_STOP_HOOK_FEEDBACK_PREFIX):
                print("[OMG] Guard 2 triggered: stop-hook feedback loop", file=sys.stderr)
                return True
        except Exception:
            pass  # Fail open — don't skip hooks on read errors

    # Guard 4: File-based loop breaker (safety net)
    #   If stop hooks have blocked multiple times in quick succession,
    #   the agent cannot meaningfully resolve the issue (likely context-limited).
    #   This is the last-resort safety net when Guards 1-3 all fail to detect the loop.
    if is_stop_block_loop():
        print("[OMG] Guard 4 triggered: stop-block loop detected, skipping hooks", file=sys.stderr)
        return True

    # Guard 5: Empty stop_reason + recent block = likely context-limit deadlock
    #   Claude Code often doesn't set stop_reason/end_turn_reason for context-limit stops.
    #   If we blocked recently (any count >= 1 within window) AND stop_reason is missing,
    #   it's almost certainly a deadlock. Allow the stop to proceed.
    if not stop_reason and not end_turn_reason:
        try:
            _pdir = get_project_dir()
            _tracker_path = os.path.join(_pdir, _STOP_BLOCK_TRACKER)
            if os.path.exists(_tracker_path):
                with open(_tracker_path, "r", encoding="utf-8") as _f:
                    _state = json.load(_f)
                _elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(_state["ts"])).total_seconds()
                if _elapsed < _BLOCK_LOOP_WINDOW_SECS and _state.get("count", 0) >= 1:
                    _reason = _state.get("reason", "unknown")
                    if _reason in _LOOP_BLOCK_REASONS:
                        print(
                            "[OMG] Guard 5 triggered: context may be exhausted and stop hooks recently blocked. "
                            "Skipping stop-hook blocks so compaction can run. "
                            "Tip: /OMG:handoff then continue in a fresh session.",
                            file=sys.stderr,
                        )
                        return True
        except Exception:
            pass  # fail open
    return False


# --- Stop-Block Loop Breaker (file-based safety net) ---

def record_stop_block(project_dir=None, reason: str = "unknown", session_id: str = ""):
    """Record that a stop hook block was issued. Called before block_decision().
    
    Args:
        project_dir: Project directory (auto-detected if None)
        reason: Human-readable reason for the block (e.g., 'ralph_loop', 'planning_gate', 'quality_check')
        session_id: Session identifier to prevent cross-session interference
    """
    try:
        pdir = project_dir or get_project_dir()
        path = os.path.join(pdir, _STOP_BLOCK_TRACKER)
        state = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "count": 1,
            "session_id": session_id,
            "reason": reason,
        }
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(old["ts"])).total_seconds()
                if elapsed < _BLOCK_LOOP_WINDOW_SECS:
                    state["count"] = old.get("count", 0) + 1
                    # Preserve session_id and reason from old state if not overridden
                    if not session_id:
                        state["session_id"] = old.get("session_id", "")
                    if reason == "unknown":
                        state["reason"] = old.get("reason", "unknown")
                # else: reset — old block is stale
            except Exception:
                pass  # intentional: corrupt file, start fresh
        atomic_json_write(path, state)
    except Exception:
        pass  # intentional: never crash on tracking


def is_stop_block_loop(project_dir=None, session_id: str = ""):
    """Return True if stop hooks have blocked repeatedly within the loop window.

    Safety net for deadlocks: if hooks blocked >= N times within M seconds,
    the agent clearly cannot resolve the issue (likely context-limited).
    All stop hooks should allow the stop to proceed.
    
    Args:
        project_dir: Project directory (auto-detected if None)
        session_id: Current session ID. If provided and tracker has a different session_id,
                   returns False (cross-session, not a loop).
    """
    try:
        pdir = project_dir or get_project_dir()
        path = os.path.join(pdir, _STOP_BLOCK_TRACKER)
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        
        # Cross-session check: if tracker has session_id and it differs from current, not a loop
        tracker_session_id = state.get("session_id", "")
        if tracker_session_id and session_id and tracker_session_id != session_id:
            return False  # Different session, not a loop
        
        ts = datetime.fromisoformat(state["ts"])
        elapsed = (datetime.now(timezone.utc) - ts).total_seconds()
        count = state.get("count", 0)
        return elapsed < _BLOCK_LOOP_WINDOW_SECS and count >= _BLOCK_LOOP_THRESHOLD
    except Exception:
        return False  # fail open — don't skip hooks on errors


def reset_stop_block_tracker(project_dir=None):
    """Reset the stop block tracker. Called on clean (non-blocked) stop."""
    try:
        pdir = project_dir or get_project_dir()
        path = os.path.join(pdir, _STOP_BLOCK_TRACKER)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass  # intentional: never crash on cleanup


def check_performance_budget(hook_name: str, elapsed_ms: float, budget_ms: float) -> bool:
    """Check if hook execution is within performance budget.
    
    Args:
        hook_name: Name of the hook being checked
        elapsed_ms: Elapsed time in milliseconds
        budget_ms: Budget threshold in milliseconds
    
    Returns:
        True if within budget, False if over budget (with warning logged)
    """
    if elapsed_ms <= budget_ms:
        return True
    # Log warning for budget overrun
    log_hook_error(
        hook_name,
        f"Performance budget exceeded: {elapsed_ms:.1f}ms > {budget_ms}ms",
        context={"elapsed_ms": elapsed_ms, "budget_ms": budget_ms}
    )
    return False
