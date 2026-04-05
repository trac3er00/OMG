#!/usr/bin/env python3
"""ConfigChange Hook: Settings Tamper Detection + Trust Review

Monitors Claude settings changes and writes Trust Review artifacts to
.omg/trust/manifest.lock.json.
"""

import json
import os
import sys
from importlib import import_module
from typing import Any

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

try:
    _common = import_module("hooks._common")
except ImportError:
    _common = import_module("_common")

setup_crash_handler = _common.setup_crash_handler
json_input = _common.json_input
_resolve_project_dir = _common._resolve_project_dir
is_bypass_mode = _common.is_bypass_mode

_file_cache: dict[str, Any] = {}


def _cached_json_load(path, *, force: bool = False):
    path_str = str(path)
    if force:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    if path_str not in _file_cache:
        with open(path, "r", encoding="utf-8") as f:
            _file_cache[path_str] = json.load(f)
    return _file_cache[path_str]


def _is_bypass_all_mode(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    mode = str(payload.get("permission_mode", "")).strip().lower()
    return mode == "bypassall"


# Compatibility marker for existing tests and policy docs.
DANGEROUS_IN_ALLOW = [
    "Bash(rm:*)",
    "Bash(sudo:*)",
    "Bash(curl:*)",
    "Bash(wget:*)",
    "Bash(ssh:*)",
    "Bash(nc:*)",
    "Bash(ncat:*)",
]

setup_crash_handler("config-guard", fail_closed=True)


def _emit_block(reason: str) -> None:
    json.dump({"decision": "block", "reason": reason}, sys.stdout)


try:
    trust_review = import_module("hooks.trust_review")
except Exception as e:
    print(
        f"[OMG] config-guard: trust_review import failed: {type(e).__name__}: {e}",
        file=sys.stderr,
    )
    _emit_block(
        "SETTINGS CHANGE DETECTED: trust review unavailable; blocked fail-closed."
    )
    sys.exit(0)

format_review_summary = trust_review.format_review_summary
regenerate_trust_manifest = trust_review.regenerate_trust_manifest

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
    try:
        project_dir = _resolve_project_dir()
        settings_path = os.path.join(project_dir, "settings.json")
        if not os.path.exists(settings_path):
            return False
        settings = _cached_json_load(settings_path)
        if isinstance(settings, dict):
            omg_config = settings.get("_omg", {})
            if isinstance(omg_config, dict):
                return omg_config.get("setup_in_progress", False)
    except Exception:
        try:
            print(
                f"[omg:warn] [config_guard] failed to detect setup-in-progress: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass
    return False


def _is_mcp_config_file(path):
    """Check if the file being changed is .mcp.json."""
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized == ".mcp.json" or normalized.endswith("/.mcp.json")


def _is_watched_config_path(path):
    return _is_watched_settings_path(path) or _is_mcp_config_file(path)


_MANDATORY_REVIEW_KEYS = {
    "hooks",
    "permissions",
    "mcp",
    "mcpservers",
    "policy",
    "allowlist",
    "denylist",
    "security",
}


def _contains_mandatory_review_surface(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in _MANDATORY_REVIEW_KEYS:
                return True
            if _contains_mandatory_review_surface(item):
                return True
    elif isinstance(value, list):
        return any(_contains_mandatory_review_surface(item) for item in value)
    return False


def _requires_mandatory_review(
    config_path: str, old_payload: Any, new_payload: Any
) -> bool:
    if _is_mcp_config_file(config_path):
        return True
    return _contains_mandatory_review_surface(
        new_payload
    ) or _contains_mandatory_review_surface(old_payload)


config_path = _extract_config_path(data)
if not config_path:
    sys.exit(0)

if not _is_watched_config_path(config_path):
    sys.exit(0)

project_dir = _resolve_project_dir()
new_path = (
    config_path
    if os.path.isabs(config_path)
    else os.path.join(project_dir, config_path)
)
if not os.path.exists(new_path):
    sys.exit(0)

try:
    new_config = _cached_json_load(new_path)
    if not isinstance(new_config, dict):
        sys.exit(0)
except Exception as e:
    print(
        f"[OMG] config-guard: config read failed: {type(e).__name__}: {e}",
        file=sys.stderr,
    )
    _emit_block("SETTINGS CHANGE DETECTED: config parse failed; blocked fail-closed.")
    sys.exit(0)

payload_old = _extract_config_object(
    data,
    ("old_config", "old_settings", "old_content", "before", "old_value"),
)

# Exemption: skip trust_review for .mcp.json changes during setup wizard
if _is_setup_in_progress() and _is_mcp_config_file(config_path):
    sys.exit(0)

if (
    is_bypass_mode(data) or _is_bypass_all_mode(data)
) and not _requires_mandatory_review(
    config_path,
    payload_old,
    new_config,
):
    sys.exit(0)

review_out = regenerate_trust_manifest(
    project_dir,
    config_path,
    old_config=payload_old if isinstance(payload_old, dict) else None,
    new_config=None,
)
review = review_out["review"]

# Backward-compatibility variable expected by tests.
hooks = new_config.get("hooks", {})
hook_count = sum(len(v) if isinstance(v, list) else 0 for v in hooks.values())

verdict = review.get("verdict", "allow")
risk_level = review.get("risk_level", "low")
summary = format_review_summary(review)
bypass_active = is_bypass_mode(data) or _is_bypass_all_mode(data)

if verdict == "deny":
    msg = "⚠ SETTINGS CHANGE DETECTED (Trust Review)\n" + summary
    msg += "\n\nBlocked because risk is critical."
    json.dump({"decision": "block", "reason": msg}, sys.stdout)
elif verdict == "ask":
    # ConfigChange hook only supports block/pass. For high-risk changes,
    # block and require explicit user re-apply after review.
    msg = "⚠ SETTINGS CHANGE REQUIRES REVIEW\n" + summary
    msg += "\n\nRe-apply after human approval."
    if risk_level == "high" or bypass_active:
        json.dump({"decision": "block", "reason": msg}, sys.stdout)
    else:
        json.dump({"decision": "pass", "reason": msg}, sys.stdout)

sys.exit(0)
