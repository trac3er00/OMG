#!/usr/bin/env python3
"""
PostToolUse Hook (*): Tool Execution Ledger (Enterprise)
Logs every tool execution to .omg/state/ledger/tool-ledger.jsonl.
Evidence trail for stop-gate.py and claim verification.
Includes log rotation to prevent unbounded growth.
"""
import json, sys, os, re, shutil, time
from datetime import datetime, timezone

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, get_project_dir
from state_migration import resolve_state_dir

setup_crash_handler("tool-ledger", fail_closed=False)

data = json_input()
_wall_start = time.monotonic()

project_dir = get_project_dir()
ledger_dir = resolve_state_dir(project_dir, "state/ledger", "ledger")
os.makedirs(ledger_dir, exist_ok=True)

ledger_path = os.path.join(ledger_dir, "tool-ledger.jsonl")

# ── Log rotation: size-only heuristic (avoids O(n) line-count scan) ──
MAX_BYTES = 5 * 1024 * 1024  # 5MB
try:
    if os.path.exists(ledger_path):
        size = os.path.getsize(ledger_path)
        needs_rotation = size > MAX_BYTES

        if needs_rotation:
            archive = ledger_path + ".1"
            # Keep only one archive
            if os.path.exists(archive):
                try:
                    os.remove(archive)
                except OSError:
                    try:
                        import sys; print(f"[omg:warn] [tool-ledger] failed to remove archive: {sys.exc_info()[1]}", file=sys.stderr)
                    except Exception:
                        pass
            shutil.move(ledger_path, archive)
except Exception:
    try:
        import sys; print(f"[omg:warn] [tool-ledger] ledger rotation failed: {sys.exc_info()[1]}", file=sys.stderr)
    except Exception:
        pass

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})
tool_response = data.get("tool_response", {})

entry = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "pid": os.getpid(),
    "tool": tool_name,
    "surface_tags": [],
}

if isinstance(tool_input, dict):
    lane_name = tool_input.get("lane_name", tool_input.get("lane"))
    if isinstance(lane_name, str) and lane_name.strip():
        entry["lane"] = lane_name.strip().lower()
        entry["surface_tags"].append("governed_tools")
    governed_tool = tool_input.get("tool_name")
    if isinstance(governed_tool, str) and governed_tool.strip() and governed_tool != tool_name:
        entry["governed_tool"] = governed_tool.strip()
        entry["surface_tags"].append("governed_tools")

# Link ledger entries to OMG v1 run/evidence artifacts when available.
run_id = os.environ.get("OMG_RUN_ID")
if not run_id:
    active_run = os.path.join(project_dir, ".omg", "shadow", "active-run")
    if os.path.exists(active_run):
        try:
            with open(active_run, "r", encoding="utf-8") as f:
                run_id = f.read().strip()
        except Exception:
            run_id = None
if run_id:
    entry["run_id"] = run_id

if tool_name == "Bash":
    entry["surface_tags"].append("hooks")
    entry["command"] = tool_input.get("command", "")[:500]
    if isinstance(tool_response, dict):
        entry["exit_code"] = tool_response.get("exitCode", tool_response.get("exit_code"))
        snippet = str(tool_response.get("stdout", ""))[:200]
        # Mask potential secrets in stdout before logging
        # Aligned with post-write.py SECRET_PATTERNS for consistent coverage
        SECRET_PATTERNS = [
            (r'(?i)(api[_-]?key|token|secret|password|passwd|credential|auth)[=:]\s*\S+', r'\1=***'),
            (r'AKIA[0-9A-Z]{16}', '***AWS_KEY***'),
            (r'(?:aws_secret_access_key|AWS_SECRET)\s*[:=]\s*[\'"]?[A-Za-z0-9/+=]{40}', '***AWS_SECRET***'),
            (r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', '***PRIVATE_KEY***'),
            (r'sk-[a-zA-Z0-9]{20,}', '***API_KEY***'),
            (r'gh[ps]_[A-Za-z0-9_]{36,}', '***GH_TOKEN***'),
            (r'github_pat_[A-Za-z0-9_]{22,}', '***GH_PAT***'),
            (r'xox[bp]-[0-9]{10,}-[A-Za-z0-9]{20,}', '***SLACK_TOKEN***'),
            (r'sk_live_[A-Za-z0-9]{20,}', '***STRIPE_KEY***'),
            (r'rk_live_[A-Za-z0-9]{20,}', '***STRIPE_KEY***'),
            (r'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]{20,}', '***SERVICE_KEY***'),
            (r'AIza[A-Za-z0-9_-]{35}', '***GOOGLE_KEY***'),
            (r'SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}', '***SENDGRID_KEY***'),
            (r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', '***JWT***'),
            (r'(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@', '***DB_URL***'),
            (r'https?://[^:]+:[^@]+@', '***URL_CREDS***'),
        ]
        for pattern, replacement in SECRET_PATTERNS:
            snippet = re.sub(pattern, replacement, snippet)
        entry["stdout_snippet"] = snippet
elif tool_name in ("Write", "Edit", "MultiEdit"):
    entry["file"] = tool_input.get("file_path", "")
    entry["success"] = tool_response.get("success") if isinstance(tool_response, dict) else None
elif tool_name == "Read":
    entry["file"] = tool_input.get("file_path", "")

# Attach the latest evidence file path if one exists for this run.
if run_id:
    ev_path = os.path.join(project_dir, ".omg", "evidence", f"{run_id}.json")
    if os.path.exists(ev_path):
        entry["evidence_path"] = os.path.relpath(ev_path, project_dir)
        entry["evidence_links"] = [entry["evidence_path"]]

if not entry["surface_tags"]:
    entry.pop("surface_tags", None)

# ── Latency tracking: duration_ms ──
# Prefer startTime/endTime from hook stdin (ISO8601), fall back to wall clock.
_duration_ms = None
try:
    _start_str = data.get("startTime")
    _end_str = data.get("endTime")
    if _start_str and _end_str:
        _st = datetime.fromisoformat(_start_str.replace("Z", "+00:00"))
        _et = datetime.fromisoformat(_end_str.replace("Z", "+00:00"))
        _duration_ms = int((_et - _st).total_seconds() * 1000)
    else:
        # Wall clock fallback
        _duration_ms = int((time.monotonic() - _wall_start) * 1000)
except Exception:
    # Malformed timestamps: fall back to wall clock, or null if that also fails
    try:
        _duration_ms = int((time.monotonic() - _wall_start) * 1000)
    except Exception:
        _duration_ms = None

entry["duration_ms"] = _duration_ms

try:
    import fcntl
    fd = open(ledger_path, "a")
    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    fd.write(json.dumps(entry, separators=(",", ":")) + "\n")
    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
    fd.close()
except (ImportError, BlockingIOError):
    try:
        with open(ledger_path, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:
        try:
            import sys; print(f"[omg:warn] [tool-ledger] fallback append failed: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass
except Exception:
    try:
        import sys; print(f"[omg:warn] [tool-ledger] append failed: {sys.exc_info()[1]}", file=sys.stderr)
    except Exception:
        pass

sys.exit(0)
