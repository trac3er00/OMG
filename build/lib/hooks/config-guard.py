#!/usr/bin/env python3
"""ConfigChange Hook: Settings Tamper Detection + Trust Review

Monitors Claude settings changes and writes Trust Review artifacts to
.omg/trust/manifest.lock.json.
"""
import contextlib
import json
import os
import sys

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, _resolve_project_dir

try:
    from _common import is_bypass_mode
except ImportError:  # pragma: no cover - compatibility with older runtimes
    def is_bypass_mode(_payload):
        return False


try:
    from _common import is_bypass_all
except ImportError:  # pragma: no cover - compatibility with older runtimes
    def is_bypass_all(_payload):
        return False

# Compatibility marker for existing tests and policy docs.
DANGEROUS_IN_ALLOW = [
    "Bash(rm:*)", "Bash(sudo:*)", "Bash(curl:*)", "Bash(wget:*)",
    "Bash(ssh:*)", "Bash(nc:*)", "Bash(ncat:*)",
]

setup_crash_handler("config-guard", fail_closed=False)

try:
    from trust_review import review_config_change, write_trust_manifest, format_review_summary
except Exception as e:
    print(f"[OMG] config-guard: trust_review import failed: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(0)

data = json_input()

def _decode_json_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except Exception:  # intentional: decode fallback
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _extract_config_path(payload):
    file_path = payload.get("file_path")
    if isinstance(file_path, str) and file_path.strip():
        return file_path

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict):
        legacy_path = tool_input.get("file_path")
        if isinstance(legacy_path, str) and legacy_path.strip():
            return legacy_path
    return ""


def _extract_config_object(payload, keys):
    for key in keys:
        parsed = _decode_json_object(payload.get(key))
        if parsed is not None:
            return parsed

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict):
        for key in keys:
            parsed = _decode_json_object(tool_input.get(key))
            if parsed is not None:
                return parsed
    return None


def _is_watched_settings_path(path):
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized == "settings.json" or normalized.endswith("/settings.json")


def _is_setup_in_progress():
    """Check if setup wizard is in progress by reading settings.json."""
    try:
        project_dir = _resolve_project_dir()
        settings_path = os.path.join(project_dir, "settings.json")
        if not os.path.exists(settings_path):
            return False
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
            if isinstance(settings, dict):
                omg_config = settings.get("_omg", {})
                if isinstance(omg_config, dict):
                    return omg_config.get("setup_in_progress", False)
    except Exception:
        pass
    return False


def _is_mcp_config_file(path):
    """Check if the file being changed is .mcp.json."""
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized == ".mcp.json" or normalized.endswith("/.mcp.json")


def _is_watched_config_path(path):
    return _is_watched_settings_path(path) or _is_mcp_config_file(path)


def _snapshot_path_for(project_dir, config_path):
    snapshot_dir = os.path.join(project_dir, ".omg", "trust")
    os.makedirs(snapshot_dir, exist_ok=True)
    filename = "last-mcp.json" if _is_mcp_config_file(config_path) else "last-settings.json"
    return os.path.join(snapshot_dir, filename)


config_path = _extract_config_path(data)
if not config_path:
    sys.exit(0)

if not _is_watched_config_path(config_path):
    sys.exit(0)

project_dir = _resolve_project_dir()
new_path = config_path if os.path.isabs(config_path) else os.path.join(project_dir, config_path)
if not os.path.exists(new_path):
    sys.exit(0)

try:
    with open(new_path, "r", encoding="utf-8") as f:
        new_config = json.load(f)
        if not isinstance(new_config, dict):
            sys.exit(0)
except Exception as e:
    print(f"[OMG] config-guard: config read failed: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(0)

# Load previous config snapshot for diff-based trust review.
snapshot_path = _snapshot_path_for(project_dir, config_path)

old_config = {}
# Prefer explicit old config in payload if present.
payload_old = _extract_config_object(
    data,
    ("old_config", "old_settings", "old_content", "before", "old_value"),
)
if isinstance(payload_old, dict):
    old_config = payload_old
elif os.path.exists(snapshot_path):
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            old_config = json.load(f)
            if not isinstance(old_config, dict):
                old_config = {}
    except Exception as e:
        print(f"[OMG] config-guard: snapshot read failed: {type(e).__name__}: {e}", file=sys.stderr)
        old_config = {}

# Prefer explicit new config when the payload provides it.
payload_new = _extract_config_object(
    data,
    ("new_config", "new_settings", "new_content", "after", "new_value"),
)
if isinstance(payload_new, dict):
    new_config = payload_new

# Exemption: skip trust_review for .mcp.json changes during setup wizard
if _is_setup_in_progress() and _is_mcp_config_file(config_path):
    sys.exit(0)

# In bypass mode, skip trust_review asks (but not denials for critical issues)
if is_bypass_mode(data) or is_bypass_all(data):
    sys.exit(0)

review = review_config_change(config_path, old_config, new_config)
write_trust_manifest(project_dir, review)

# Keep a rolling snapshot for next review.
with contextlib.suppress(OSError):  # intentional: cleanup
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(new_config, f, indent=2, ensure_ascii=True)

# Backward-compatibility variable expected by tests.
hooks = new_config.get("hooks", {})
hook_count = sum(len(v) if isinstance(v, list) else 0 for v in hooks.values())

verdict = review.get("verdict", "allow")
risk_level = review.get("risk_level", "low")
summary = format_review_summary(review)

if verdict == "deny":
    msg = "⚠ SETTINGS CHANGE DETECTED (Trust Review)\n" + summary
    msg += "\n\nBlocked because risk is critical."
    json.dump({"decision": "block", "reason": msg}, sys.stdout)
elif verdict == "ask":
    # ConfigChange hook only supports block/pass. For high-risk changes,
    # block and require explicit user re-apply after review.
    msg = "⚠ SETTINGS CHANGE REQUIRES REVIEW\n" + summary
    msg += "\n\nRe-apply after human approval."
    if risk_level == "high":
        json.dump({"decision": "block", "reason": msg}, sys.stdout)

sys.exit(0)
