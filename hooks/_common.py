"""Shared utilities for OMG hooks. Pure stdlib — no external deps."""
from __future__ import annotations

import json
import os
import sys
import fcntl
import site
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- Stop-Block Loop Breaker ---
_STOP_BLOCK_TRACKER = ".omg/state/ledger/.stop-block-tracker.json"
# Max seconds between blocks to consider it a loop
_BLOCK_LOOP_WINDOW_SECS = 30
# How many consecutive blocks before we skip
_BLOCK_LOOP_THRESHOLD = 2
# Block reasons that indicate a loop scenario (Guard 5 skip-eligible)
_LOOP_BLOCK_REASONS = {"planning_gate", "ralph_loop", "quality_check", "block_decision", "unknown", "circuit_breaker_hard_stop"}

# --- Hook Reentry Guard ---
_HOOK_REENTRY_LOCK_DIR = ".omg/state/ledger"

# --- Performance Budget Constants ---
PRE_TOOL_INJECT_MAX_MS = 100
STOP_CHECK_MAX_MS = 15000
STOP_DISPATCHER_TOTAL_MAX_MS = 90000

_file_cache: dict[str, object] = {}


def _cached_json_load(path, *, force: bool = False):
    path_str = str(path)
    if force:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    if path_str not in _file_cache:
        with open(path, "r", encoding="utf-8") as f:
            _file_cache[path_str] = json.load(f)
    return _file_cache[path_str]


def _managed_site_packages(runtime_root: Path) -> list[Path]:
    venv_root = runtime_root / ".venv"
    if not venv_root.is_dir():
        return []

    candidates: list[Path] = []
    for pattern in ("lib/python*/site-packages", "Lib/site-packages"):
        for path in venv_root.glob(pattern):
            if path.is_dir():
                candidates.append(path.resolve())
    return candidates


def bootstrap_runtime_paths(anchor: str | os.PathLike[str] | None = None) -> None:
    """Add the repo root or portable omg-runtime root to ``sys.path``.

    Installed hooks live under ``~/.claude/hooks`` while the portable runtime is
    provisioned under ``~/.claude/omg-runtime``. Repo-local execution instead
    keeps ``hooks/``, ``runtime/``, ``lab/`` and related packages side by side.
    This helper resolves both layouts and is safe to call repeatedly.
    """
    _claude_dir = Path(os.path.expanduser("~/.claude"))
    if (_claude_dir / ".omg-uninstalling").exists():
        sys.exit(0)

    anchor_path = Path(anchor).resolve() if anchor is not None else Path(__file__).resolve()
    hooks_dir = anchor_path.parent
    parent_dir = hooks_dir.parent

    candidates: list[Path] = [hooks_dir]
    for candidate in (
        parent_dir,
        parent_dir / "omg-runtime",
        hooks_dir / "omg-runtime",
    ):
        if candidate not in candidates:
            candidates.append(candidate)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if project_dir:
        project_path = Path(project_dir).resolve()
        for candidate in (
            project_path,
            project_path / "omg-runtime",
        ):
            if candidate not in candidates:
                candidates.append(candidate)

    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate.is_dir() and candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
        for site_packages in _managed_site_packages(candidate):
            site.addsitedir(str(site_packages))


bootstrap_runtime_paths()

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


def block_decision(reason, *, block_reason="unknown", project_dir=None):
    """Emit a Stop hook block decision to stdout.

    Also records the block for loop detection. Every stop hook that calls
    block_decision() contributes to the loop breaker counter, so deadlocks
    are detected regardless of which specific hook triggers the block.
    """
    # Record block BEFORE emitting -- ensures tracker is updated even if
    # the process is killed after emitting the decision.
    try:
        record_stop_block(project_dir=project_dir, reason=block_reason)
    except Exception:
        try:
            print(f"[omg:warn] failed to record stop block before decision: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass
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
                try:
                    print(f"[omg:warn] failed to emit deny decision from crash handler: {sys.exc_info()[1]}", file=sys.stderr)
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
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "hook": hook_name,
            "error": str(error),
        }
        if context:
            entry["context"] = context
        line = json.dumps(entry, separators=(",", ":")) + "\n"

        try:
            with _locked_path(ledger_path):
                if os.path.exists(ledger_path) and os.path.getsize(ledger_path) > 100 * 1024:
                    archive = ledger_path + ".1"
                    if os.path.exists(archive):
                        try:
                            os.remove(archive)
                        except OSError:
                            try:
                                print(f"[omg:warn] failed to remove archived hook error ledger: {sys.exc_info()[1]}", file=sys.stderr)
                            except Exception:
                                pass
                    try:
                        os.rename(ledger_path, archive)
                    except OSError:
                        try:
                            print(f"[omg:warn] failed to rotate hook error ledger archive: {sys.exc_info()[1]}", file=sys.stderr)
                        except Exception:
                            pass

                fd = os.open(
                    ledger_path,
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND | _O_NOFOLLOW_HOOKS,
                    0o600,
                )
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.seek(0, os.SEEK_END)
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
        except Exception as e:
            print(f"[OMG] _common.py: {type(e).__name__}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[OMG] _common.py: {type(e).__name__}: {e}", file=sys.stderr)


_O_NOFOLLOW_HOOKS: int = getattr(os, "O_NOFOLLOW", 0)


def _fsync_dir_hooks(dirpath):
    fd = os.open(dirpath, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _locked_path(path):
    lock_path = path + ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | _O_NOFOLLOW_HOOKS, 0o600)
    lock_acquired = False
    try:
        # Fast path: non-blocking attempts with exponential backoff (total ~70ms)
        # Optimizes for uncontended case while avoiding long stalls
        for delay in (0.01, 0.02, 0.04):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_acquired = True
                break
            except BlockingIOError:
                time.sleep(delay)

        # Slow path: if still contended after backoff, use blocking lock
        # This guarantees acquisition and preserves correctness
        if not lock_acquired:
            fcntl.flock(fd, fcntl.LOCK_EX)
            lock_acquired = True

        yield lock_path
    finally:
        try:
            if lock_acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextmanager
def hook_reentry_guard(hook_name):
    """Prevent concurrent execution of the same hook.

    Uses LOCK_NB with 3 retries at 0.1s intervals, then fails open (yields True).
    Writes PID + timestamp to lock file while held.

    Yields:
        True if guard acquired (proceed), False if another instance running (skip).
    """
    project_dir = get_project_dir()
    lock_dir = os.path.join(project_dir, _HOOK_REENTRY_LOCK_DIR)
    os.makedirs(lock_dir, exist_ok=True)
    lock_file = os.path.join(lock_dir, f".{hook_name}.reentry.lock")

    fd = None
    acquired = False
    fail_open = False

    try:
        fd = os.open(lock_file, os.O_RDWR | os.O_CREAT | _O_NOFOLLOW_HOOKS, 0o600)
        for _ in range(3):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                time.sleep(0.1)
    except Exception:
        # Fail-open: couldn't open/lock the file
        fail_open = True

    if not acquired and not fail_open:
        # Another instance is running, signal caller to skip
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                try:
                    print(f"[omg:warn] failed to close reentry guard lock fd on skip: {sys.exc_info()[1]}", file=sys.stderr)
                except Exception:
                    pass
            fd = None
        yield False
        return

    if acquired:
        assert fd is not None
        try:
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, json.dumps({"pid": os.getpid(), "ts": time.time()}).encode("utf-8"))
        except Exception:
            try:
                print(f"[omg:warn] failed to write reentry guard diagnostics: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass

    try:
        yield True  # Either lock acquired or fail-open
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                try:
                    print(f"[omg:warn] failed to unlock reentry guard lock: {sys.exc_info()[1]}", file=sys.stderr)
                except Exception:
                    pass
            try:
                os.close(fd)
            except Exception:
                try:
                    print(f"[omg:warn] failed to close reentry guard lock fd: {sys.exc_info()[1]}", file=sys.stderr)
                except Exception:
                    pass


def atomic_json_write(path, data):
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if os.path.islink(path):
            raise OSError(f"Symlink target rejected: {path}")

        tmp_path = path + ".tmp"
        if os.path.islink(tmp_path):
            raise OSError(f"Symlink tmp path rejected: {tmp_path}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

        content = json.dumps(data, separators=(",", ":")).encode("utf-8")
        open_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW_HOOKS
        fd = os.open(tmp_path, open_flags, 0o600)
        try:
            written = 0
            while written < len(content):
                written += os.write(fd, content[written:])
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                try:
                    print(f"[omg:warn] failed to clean up atomic write temp file: {sys.exc_info()[1]}", file=sys.stderr)
                except Exception:
                    pass
            raise
        else:
            os.close(fd)

        os.replace(tmp_path, path)
        _fsync_dir_hooks(parent or ".")
    except Exception as e:
        print(f"[OMG] _common.py: {type(e).__name__}: {e}", file=sys.stderr)


def write_checklist_session(project_dir, session_id=None):
    """Persist session metadata for the active planning checklist."""
    if not session_id:
        session_id = _get_session_id()
    sidecar = os.path.join(project_dir, ".omg", "state", "_checklist.session")
    atomic_json_write(sidecar, {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def read_checklist_session(project_dir):
    """Read planning checklist session metadata."""
    sidecar = os.path.join(project_dir, ".omg", "state", "_checklist.session")
    try:
        if os.path.exists(sidecar):
            with open(sidecar, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                return payload
    except Exception:
        try:
            print(f"[omg:warn] failed to read checklist session sidecar: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass
    return None


def _parse_hook_timestamp(raw_value: str):
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def has_recent_tool_activity(project_dir, since_minutes=60):
    """Summarize recent tool-ledger activity for planning-gate advisories."""
    result = {"has_writes": False, "has_tests": False, "tool_count": 0}
    ledger = os.path.join(project_dir, ".omg", "state", "ledger", "tool-ledger.jsonl")
    if not os.path.exists(ledger):
        return result
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        with open(ledger, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if not isinstance(entry, dict):
                    continue
                ts = _parse_hook_timestamp(entry.get("ts", ""))
                if ts is not None and ts < cutoff:
                    continue
                result["tool_count"] += 1
                tool = str(entry.get("tool", ""))
                if tool in ("Write", "Edit", "MultiEdit"):
                    result["has_writes"] = True
                command = str(entry.get("command", "")).lower()
                if any(kw in command for kw in ("test", "lint", "check", "build", "pytest", "jest", "vitest")):
                    result["has_tests"] = True
    except OSError:
        try:
            print(f"[omg:warn] failed to scan recent tool activity ledger: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass
    return result


# Feature flags cache — read settings.json once per hook invocation
_FEATURE_CACHE = {}
_settings_preset = None
_feature_settings_loaded = False
_settings_cache: dict[str, object] | None = None
_settings_cache_loaded = False
_MANAGED_PRESET_FLAGS = {
    "SETUP",
    "SETUP_WIZARD",
    "MEMORY_AUTOSTART",
    "SESSION_ANALYTICS",
    "CONTEXT_MANAGER",
    "COST_TRACKING",
    "MEMORY_SERVER",
    "GIT_WORKFLOW",
    "TEST_GENERATION",
    "DEP_HEALTH",
    "CODEBASE_VIZ",
    "DATA_ENFORCEMENT",
    "WEB_ENFORCEMENT",
    "TERMS_ENFORCEMENT",
    "COUNCIL_ROUTING",
    "FORGE_ALL_DOMAINS",
    "NOTEBOOKLM",
    "auto_compact",
}
_PRESET_FEATURES = {
    "safe": {flag: False for flag in _MANAGED_PRESET_FLAGS},
    "balanced": {
        "SETUP": True,
        "SETUP_WIZARD": True,
        "MEMORY_AUTOSTART": True,
        "SESSION_ANALYTICS": True,
        "CONTEXT_MANAGER": True,
        "COST_TRACKING": True,
        "MEMORY_SERVER": False,
        "GIT_WORKFLOW": False,
        "TEST_GENERATION": False,
        "DEP_HEALTH": False,
        "CODEBASE_VIZ": False,
        "auto_compact": True,
    },
    "interop": {
        "SETUP": True,
        "SETUP_WIZARD": True,
        "MEMORY_AUTOSTART": True,
        "SESSION_ANALYTICS": True,
        "CONTEXT_MANAGER": True,
        "COST_TRACKING": True,
        "MEMORY_SERVER": True,
        "GIT_WORKFLOW": False,
        "TEST_GENERATION": False,
        "DEP_HEALTH": False,
        "CODEBASE_VIZ": False,
        "auto_compact": True,
    },
    "labs": {
        "SETUP": True,
        "SETUP_WIZARD": True,
        "MEMORY_AUTOSTART": True,
        "SESSION_ANALYTICS": True,
        "CONTEXT_MANAGER": True,
        "COST_TRACKING": True,
        "MEMORY_SERVER": True,
        "GIT_WORKFLOW": True,
        "TEST_GENERATION": True,
        "DEP_HEALTH": True,
        "CODEBASE_VIZ": True,
        "DATA_ENFORCEMENT": False,
        "WEB_ENFORCEMENT": False,
        "TERMS_ENFORCEMENT": False,
        "COUNCIL_ROUTING": False,
        "FORGE_ALL_DOMAINS": False,
        "NOTEBOOKLM": False,
        "auto_compact": True,
    },
    "buffet": {flag: True for flag in _MANAGED_PRESET_FLAGS},
    "production": {flag: True for flag in _MANAGED_PRESET_FLAGS},
}
_FEATURE_ALIASES = {
    "SETUP": ("SETUP", "SETUP_WIZARD"),
    "SETUP_WIZARD": ("SETUP_WIZARD", "SETUP"),
}


def _load_feature_settings():
    """Populate feature cache from settings.json and return the configured preset."""
    global _settings_preset, _feature_settings_loaded

    _FEATURE_CACHE.clear()
    _settings_preset = None
    _feature_settings_loaded = False
    try:
        settings = get_settings()
        if isinstance(settings, dict):
            omg = settings.get("_omg", {})
            if isinstance(omg, dict):
                features = omg.get("features", {})
                if isinstance(features, dict):
                    _FEATURE_CACHE.update(features)
                preset = omg.get("preset")
                if isinstance(preset, str) and preset in _PRESET_FEATURES:
                    _settings_preset = preset
    except Exception:
        try:
            print(f"[omg:warn] failed to load feature settings from settings.json: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass
    finally:
        _feature_settings_loaded = True


def get_settings(force: bool = False):
    global _settings_cache, _settings_cache_loaded

    if force:
        _settings_cache_loaded = False

    if not _settings_cache_loaded:
        settings_path = os.path.join(get_project_dir(), "settings.json")
        loaded: dict[str, object] = {}
        if os.path.exists(settings_path):
            data = _cached_json_load(settings_path, force=force)
            if isinstance(data, dict):
                loaded = data
        _settings_cache = loaded
        _settings_cache_loaded = True

    if isinstance(_settings_cache, dict):
        return _settings_cache
    return {}


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
    if not _feature_settings_loaded:
        _load_feature_settings()

    env_preset = os.environ.get("OMG_PRESET", "").lower().strip()
    lookup_names = _FEATURE_ALIASES.get(flag_name, (flag_name,))

    # Env preset is a session-scoped override for managed flags.
    if env_preset in _PRESET_FEATURES:
        for name in lookup_names:
            if name in _MANAGED_PRESET_FLAGS:
                return _PRESET_FEATURES[env_preset].get(name, default)

    for name in lookup_names:
        if name in _FEATURE_CACHE:
            return _FEATURE_CACHE[name]

    if _settings_preset in _PRESET_FEATURES:
        for name in lookup_names:
            if name in _MANAGED_PRESET_FLAGS:
                return _PRESET_FEATURES[_settings_preset].get(name, default)

    return default


# Permission mode helpers
BYPASS_MODES = frozenset({"bypasspermissions", "dontask"})
EDIT_BYPASS_MODES = frozenset({"bypasspermissions", "dontask", "acceptedits"})


def _get_permission_mode(data):
    """Normalize and extract permission_mode from hook input."""
    if not isinstance(data, dict):
        return ""
    return (data.get("permission_mode") or "").lower().strip()


def is_bypass_mode(data):
    """Return True if the hook input indicates permission prompts should be skipped.

    Claude Code passes ``permission_mode`` in the hook input.  When the user
    enables *bypass permissions* or *don't ask* mode, hooks should still
    enforce hard denials (critical safety) but must NOT emit ``ask`` decisions
    that would re-introduce confirmation prompts.
    """
    if not isinstance(data, dict):
        return False
    mode = _get_permission_mode(data)
    return mode in BYPASS_MODES


def is_edit_bypass_mode(data):
    """Return True if the hook input indicates edit prompts should be skipped.

    Includes ``acceptedits`` in addition to the full bypass modes — this mode
    auto-approves file edits but still prompts for other tool uses.
    """
    if not isinstance(data, dict):
        return False
    mode = _get_permission_mode(data)
    return mode in EDIT_BYPASS_MODES


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
    failure_reason = str(data.get("failure_reason", data.get("failureReason", ""))).lower()
    signal_text = " ".join(part for part in (stop_reason, end_turn_reason, failure_reason) if part)
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
            try:
                print(f"[omg:warn] failed to inspect transcript for stop-hook feedback loop: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass

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
    if not stop_reason and not end_turn_reason and not failure_reason:
        try:
            _pdir = get_project_dir()
            _tracker_path = os.path.join(_pdir, _STOP_BLOCK_TRACKER)
            if os.path.exists(_tracker_path):
                with open(_tracker_path, "r", encoding="utf-8") as _f:
                    _state = json.load(_f)
                # Session isolation: stale tracker from another session cannot suppress hooks
                _tracker_session = _state.get("session_id", "")
                _current_session = _get_session_id()
                if (_tracker_session and _current_session != "unknown"
                        and _tracker_session != _current_session):
                    pass  # Different session — not a deadlock
                else:
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
            try:
                print(f"[omg:warn] failed to evaluate guard 5 stop-block tracker state: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass
    return False


# --- Stop-Block Loop Breaker (file-based safety net) ---


def _get_session_id():
    """Get current session ID from environment, falling back to 'unknown'."""
    for key in ("CLAUDE_SESSION_ID", "SESSION_ID", "OMG_SESSION_ID"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return "unknown"


def record_stop_block(project_dir=None, reason: str = "unknown", session_id: str = ""):
    """Record that a stop hook block was issued. Called before block_decision().

    Args:
        project_dir: Project directory (auto-detected if None)
        reason: Human-readable reason for the block (e.g., 'ralph_loop', 'planning_gate', 'quality_check')
        session_id: Session identifier to prevent cross-session interference
    """
    try:
        current_session_id = session_id or _get_session_id()
        pdir = project_dir or get_project_dir()
        path = os.path.join(pdir, _STOP_BLOCK_TRACKER)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        state = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "count": 1,
            "session_id": current_session_id,
            "reason": reason,
        }
        with _locked_path(path):
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        old = json.load(f)
                    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(old["ts"])).total_seconds()
                    if elapsed < _BLOCK_LOOP_WINDOW_SECS:
                        state["count"] = old.get("count", 0) + 1
                        if current_session_id == "unknown":
                            state["session_id"] = old.get("session_id", "unknown")
                        if reason == "unknown":
                            state["reason"] = old.get("reason", "unknown")
                except Exception:
                    try:
                        print(f"[omg:warn] failed to parse existing stop-block tracker; starting fresh: {sys.exc_info()[1]}", file=sys.stderr)
                    except Exception:
                        pass
            atomic_json_write(path, state)
    except Exception:
        try:
            print(f"[omg:warn] failed to persist stop-block tracker state: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass


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
        if not session_id:
            session_id = _get_session_id()
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
        try:
            print(f"[omg:warn] failed to reset stop-block tracker: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass


_SESSION_SLUG_ADJECTIVES = [
    "swift", "calm", "bold", "keen", "warm", "deep", "bright", "clear",
    "sharp", "steady", "quiet", "agile", "vivid", "crisp", "fresh",
    "noble", "rapid", "fluid", "light", "wise",
]
_SESSION_SLUG_NOUNS = [
    "falcon", "cedar", "river", "summit", "bridge", "beacon", "anchor",
    "compass", "harbor", "prism", "atlas", "forge", "spark", "orbit",
    "pulse", "nexus", "ridge", "bloom", "drift", "flame",
]


def generate_session_slug():
    """Generate a human-readable session slug: '{adjective}-{noun}-{YYYYMMDD}'."""
    import random
    adj = random.choice(_SESSION_SLUG_ADJECTIVES)
    noun = random.choice(_SESSION_SLUG_NOUNS)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{adj}-{noun}-{date_str}"


import shutil as _shutil

_codex_available: bool | None = None


def detect_codex_available() -> bool:
    """Detect if Codex CLI is available on this system.

    Checks: 1) `codex` binary in PATH, 2) `.agents/` directory exists in project.
    Result is cached for the process lifetime.
    """
    global _codex_available
    if _codex_available is not None:
        return _codex_available

    # Check 1: codex binary in PATH
    if _shutil.which("codex"):
        _codex_available = True
        return True

    # Check 2: .agents/ directory in project (Codex workspace indicator)
    try:
        project_dir = get_project_dir()
        if os.path.isdir(os.path.join(project_dir, ".agents")):
            _codex_available = True
            return True
    except Exception:
        try:
            print(f"[omg:warn] failed to probe .agents directory for codex availability: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass

    _codex_available = False
    return False


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
