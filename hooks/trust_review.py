#!/usr/bin/env python3
"""OMG v1 Trust Review

Analyzes high-risk configuration changes (hooks/MCP/env/permissions) and emits
structured trust review artifacts. Also integrates with config discovery to
validate and approve discovered AI tool configurations.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import re
import sys

DANGEROUS_ALLOW_COMMANDS = (
    "rm",
    "sudo",
    "curl",
    "wget",
    "ssh",
    "nc",
    "ncat",
)

_LATEST_TAG_PATTERN = re.compile(r"@latest(?:$|[/:])", re.IGNORECASE)
_SETTINGS_FILE = "settings.json"
_MCP_FILE = ".mcp.json"


def _is_dangerous_allow_entry(entry: Any) -> bool:
    if not isinstance(entry, str):
        return False

    normalized = re.sub(r"\s+", " ", entry.strip())
    for command in DANGEROUS_ALLOW_COMMANDS:
        patterns = (
            f"Bash({command}:*)",
            f"Bash({command} *)",
        )
        if normalized in patterns:
            return True

    return False


def _mcp_server_risk(server_name: str, config: Any) -> tuple[int, list[str], list[str]]:
    if not isinstance(config, dict):
        return 0, [], []

    score = 0
    reasons: list[str] = []
    controls: list[str] = []

    command = str(config.get("command", "")).strip()
    args = config.get("args", [])
    args_list = [str(arg) for arg in args] if isinstance(args, list) else []

    if command == "npx" and any(arg in {"-y", "--yes"} for arg in args_list):
        score += 35
        reasons.append(f"MCP server {server_name} uses npx auto-install confirmation")
        controls.append("pin-mcp-package")

    if any(_LATEST_TAG_PATTERN.search(arg) for arg in args_list):
        score += 45
        reasons.append(f"MCP server {server_name} uses an unpinned @latest package")
        controls.append("pin-mcp-package")

    if "server-filesystem" in " ".join(args_list):
        root = args_list[-1] if args_list else ""
        if root not in {".", "./"}:
            score += 45
            reasons.append(f"MCP filesystem server {server_name} is scoped outside the project root")
            controls.append("scope-filesystem-root")

    return score, reasons, controls


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _collect_mcp_changes(old_cfg: dict[str, Any], new_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    old_servers = _safe_dict(old_cfg.get("mcpServers"))
    new_servers = _safe_dict(new_cfg.get("mcpServers"))
    changes: list[dict[str, Any]] = []

    old_keys = set(old_servers.keys())
    new_keys = set(new_servers.keys())

    for name in sorted(new_keys - old_keys):
        changes.append({"type": "added", "server": name, "new": new_servers.get(name)})
    for name in sorted(old_keys - new_keys):
        changes.append({"type": "removed", "server": name, "old": old_servers.get(name)})
    for name in sorted(old_keys & new_keys):
        if old_servers.get(name) != new_servers.get(name):
            changes.append(
                {
                    "type": "modified",
                    "server": name,
                    "old": old_servers.get(name),
                    "new": new_servers.get(name),
                }
            )
    return changes


def _count_hooks(cfg: dict[str, Any]) -> int:
    hooks = _safe_dict(cfg.get("hooks"))
    total = 0
    for event_entries in hooks.values():
        if not isinstance(event_entries, list):
            continue
        for entry in event_entries:
            if isinstance(entry, dict):
                nested = _safe_list(entry.get("hooks"))
                total += len(nested) if nested else 1
            else:
                total += 1
    return total


def _collect_hook_changes(old_cfg: dict[str, Any], new_cfg: dict[str, Any]) -> dict[str, Any]:
    old_hooks = _safe_dict(old_cfg.get("hooks"))
    new_hooks = _safe_dict(new_cfg.get("hooks"))

    old_events = set(old_hooks.keys())
    new_events = set(new_hooks.keys())
    removed_events = sorted(old_events - new_events)
    added_events = sorted(new_events - old_events)
    modified_events = sorted(
        event for event in (old_events & new_events) if old_hooks.get(event) != new_hooks.get(event)
    )

    return {
        "old_hook_count": _count_hooks(old_cfg),
        "new_hook_count": _count_hooks(new_cfg),
        "removed_events": removed_events,
        "added_events": added_events,
        "modified_events": modified_events,
    }


def _collect_env_changes(old_cfg: dict[str, Any], new_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    old_env = _safe_dict(old_cfg.get("env"))
    new_env = _safe_dict(new_cfg.get("env"))

    changes: list[dict[str, Any]] = []
    keys = sorted(set(old_env.keys()) | set(new_env.keys()))
    for key in keys:
        old = old_env.get(key)
        new = new_env.get(key)
        if old == new:
            continue
        changes.append({"key": key, "old": old, "new": new})
    return changes


def _risk_from_permissions(old_cfg: dict[str, Any], new_cfg: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    old_perms = _safe_dict(old_cfg.get("permissions"))
    new_perms = _safe_dict(new_cfg.get("permissions"))

    old_allow = set(_safe_list(old_perms.get("allow")))
    new_allow = set(_safe_list(new_perms.get("allow")))
    added_allow = sorted(new_allow - old_allow)

    score = 0
    reasons: list[str] = []
    controls: list[str] = []

    for dangerous in added_allow:
        if _is_dangerous_allow_entry(dangerous):
            score += 80
            reasons.append(f"Dangerous allow pattern added: {dangerous}")
            controls.extend(["manual-trust-review", "deny-by-default"])

    return score, reasons, controls


def _risk_from_hooks(hook_changes: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    controls: list[str] = []

    old_count = int(hook_changes.get("old_hook_count", 0))
    new_count = int(hook_changes.get("new_hook_count", 0))
    removed_events = hook_changes.get("removed_events", [])
    modified_events = hook_changes.get("modified_events", [])

    if old_count and new_count < max(1, old_count - 2):
        score += 35
        reasons.append(f"Hook count reduced significantly ({old_count} -> {new_count})")
        controls.append("require-hook-audit")

    if removed_events:
        score += 25
        reasons.append(f"Hook events removed: {', '.join(removed_events)}")
        controls.append("event-removal-review")

    if modified_events:
        score += 20
        reasons.append(f"Hook definitions modified: {', '.join(modified_events)}")
        controls.append("hook-diff-review")

    return score, reasons, controls


def _risk_from_mcp(mcp_changes: list[dict[str, Any]]) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    controls: list[str] = []

    for change in mcp_changes:
        ctype = change.get("type")
        name = change.get("server")
        server_cfg = change.get("new") if ctype in {"added", "modified"} else change.get("old")
        if ctype == "added":
            score += 30
            reasons.append(f"New MCP server added: {name}")
            controls.append("mcp-endpoint-review")
        elif ctype == "modified":
            score += 35
            reasons.append(f"MCP server modified: {name}")
            controls.append("mcp-diff-review")
        elif ctype == "removed":
            score += 10
            reasons.append(f"MCP server removed: {name}")

        extra_score, extra_reasons, extra_controls = _mcp_server_risk(str(name), server_cfg)
        score += extra_score
        reasons.extend(extra_reasons)
        controls.extend(extra_controls)

    return score, reasons, controls


def _risk_from_env(env_changes: list[dict[str, Any]]) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    controls: list[str] = []

    for change in env_changes:
        key = str(change.get("key", ""))
        if any(token in key.upper() for token in ["KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"]):
            score += 20
            reasons.append(f"Sensitive environment key modified: {key}")
            controls.append("secret-env-review")
        else:
            score += 5
            reasons.append(f"Environment key modified: {key}")

    return score, reasons, controls


def score_to_verdict(score: int) -> tuple[str, str]:
    if score >= 80:
        return "deny", "critical"
    if score >= 45:
        return "ask", "high"
    if score >= 20:
        return "ask", "med"
    return "allow", "low"


def review_config_change(
    file_path: str,
    old_config: dict[str, Any] | None,
    new_config: dict[str, Any] | None,
) -> dict[str, Any]:
    old_cfg = old_config or {}
    new_cfg = new_config or {}

    mcp_changes = _collect_mcp_changes(old_cfg, new_cfg)
    hook_changes = _collect_hook_changes(old_cfg, new_cfg)
    env_changes = _collect_env_changes(old_cfg, new_cfg)

    risk_score = 0
    reasons: list[str] = []
    controls: list[str] = []

    for score, r, c in [
        _risk_from_permissions(old_cfg, new_cfg),
        _risk_from_hooks(hook_changes),
        _risk_from_mcp(mcp_changes),
        _risk_from_env(env_changes),
    ]:
        risk_score += score
        reasons.extend(r)
        controls.extend(c)

    verdict, risk_level = score_to_verdict(risk_score)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "changed_files": [file_path] if file_path else [],
        "mcp_changes": mcp_changes,
        "hook_changes": hook_changes,
        "env_changes": env_changes,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "verdict": verdict,
        "reasons": reasons,
        "controls": sorted(set(controls)),
    }


def format_review_summary(review: dict[str, Any]) -> str:
    verdict = review.get("verdict", "allow")
    score = review.get("risk_score", 0)
    risk_level = review.get("risk_level", "low")
    reasons = review.get("reasons", []) or []

    lines = [f"Trust Review: verdict={verdict} risk={risk_level} score={score}"]
    if reasons:
        lines.extend([f"  - {reason}" for reason in reasons[:6]])
    return "\n".join(lines)


def write_trust_manifest(project_dir: str, review: dict[str, Any]) -> str:
    trust_dir = os.path.join(project_dir, ".omg", "trust")
    os.makedirs(trust_dir, exist_ok=True)
    manifest_path = os.path.join(trust_dir, "manifest.lock.json")

    payload = {
        "version": "omg-v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_review": review,
    }
    digest_input = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["signature"] = hashlib.sha256(digest_input).hexdigest()

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)

    return manifest_path


def _is_mcp_config_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").rstrip("/")
    return normalized == _MCP_FILE or normalized.endswith(f"/{_MCP_FILE}")


def _canonical_config_path(file_path: str) -> str:
    if _is_mcp_config_path(file_path):
        return _MCP_FILE

    normalized = str(file_path or "").replace("\\", "/").rstrip("/")
    if normalized == _SETTINGS_FILE or normalized.endswith(f"/{_SETTINGS_FILE}"):
        return _SETTINGS_FILE

    return normalized or _SETTINGS_FILE


def _trust_snapshot_path(project_dir: str, config_path: str) -> str:
    trust_dir = os.path.join(project_dir, ".omg", "trust")
    os.makedirs(trust_dir, exist_ok=True)
    filename = "last-mcp.json" if _is_mcp_config_path(config_path) else "last-settings.json"
    return os.path.join(trust_dir, filename)


def _resolve_live_config(project_dir: str, config_path: str) -> dict[str, Any]:
    rel_path = _canonical_config_path(config_path)
    abs_path = rel_path if os.path.isabs(rel_path) else os.path.join(project_dir, rel_path)
    return _load_json_file(abs_path)


def regenerate_trust_manifest(
    project_dir: str,
    file_path: str,
    old_config: dict[str, Any] | None = None,
    new_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical_path = _canonical_config_path(file_path)
    snapshot_path = _trust_snapshot_path(project_dir, canonical_path)

    previous_cfg = old_config if isinstance(old_config, dict) else _load_json_file(snapshot_path)
    current_cfg = new_config if isinstance(new_config, dict) else _resolve_live_config(project_dir, canonical_path)

    review = review_config_change(canonical_path, previous_cfg, current_cfg)
    manifest_path = write_trust_manifest(project_dir, review)

    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(current_cfg, f, indent=2, ensure_ascii=True)

    return {
        "review": review,
        "manifest_path": manifest_path,
        "snapshot_path": snapshot_path,
        "canonical_path": canonical_path,
    }


def _load_json_file(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}



# === Config Discovery Integration ============================================

# Suspicious code patterns that should block config import
_DANGEROUS_PATTERNS = [
    re.compile(r'\beval\s*\('),
    re.compile(r'\bexec\s*\('),
    re.compile(r'\b__import__\s*\('),
    re.compile(r'\bsubprocess\b'),
    re.compile(r'\bos\.system\s*\('),
]

# Credential patterns that produce warnings (not blocking)
_CREDENTIAL_PATTERNS = [
    re.compile(r'\bpassword\b', re.IGNORECASE),
    re.compile(r'\bsecret\b', re.IGNORECASE),
    re.compile(r'\bapi_key\b', re.IGNORECASE),
    re.compile(r'\btoken\b', re.IGNORECASE),
]

# Max config size before warning (100KB)
_MAX_CONFIG_SIZE_BYTES = 100 * 1024


def _validate_config_security(config_path: str, content: str) -> Dict[str, Any]:
    """Validate a config file's content for security issues.

    Returns:
        {"safe": bool, "issues": list[str], "warnings": list[str]}
    """
    issues: List[str] = []
    warnings: List[str] = []

    # Check for dangerous code patterns
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(content):
            issues.append(f"Dangerous pattern '{pattern.pattern}' found in {config_path}")

    # Check for credential patterns (warn only)
    for pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(content):
            warnings.append(f"Credential pattern '{pattern.pattern}' found in {config_path}")

    # Check file size
    try:
        size = os.path.getsize(config_path) if os.path.isfile(config_path) else 0
        if size > _MAX_CONFIG_SIZE_BYTES:
            warnings.append(f"Config file is large ({size} bytes): {config_path}")
    except OSError:
        pass

    return {
        "safe": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


def _log_config_import(config_path: str, tool: str, approved: bool, project_dir: str = ".") -> None:
    """Log a config import decision to .omg/trust/config_imports.json.

    Uses atomic_json_write() from _common for safe writes.
    """
    # Lazy import _common utilities
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        common_module = importlib.import_module("hooks._common")
    except ImportError:
        try:
            common_module = importlib.import_module("_common")
        except ImportError:
            return  # silently fail if _common unavailable
    try:
        atomic_json_write = common_module.atomic_json_write
    except AttributeError:
        return  # silently fail if _common unavailable

    # Compute SHA-256 hash of the config file
    sha256_hash = ""
    try:
        abs_path = os.path.join(project_dir, config_path) if not os.path.isabs(config_path) else config_path
        if os.path.isfile(abs_path):
            with open(abs_path, "rb") as f:
                sha256_hash = hashlib.sha256(f.read()).hexdigest()
    except (OSError, IOError):
        sha256_hash = "unreadable"

    # Build log entry
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config_path": config_path,
        "tool": tool,
        "approved": approved,
        "sha256_hash": sha256_hash,
    }

    # Load existing log, append, write back
    log_path = os.path.join(project_dir, ".omg", "trust", "config_imports.json")
    existing: List[Dict[str, Any]] = []
    try:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing = data
    except (json.JSONDecodeError, OSError):
        existing = []

    existing.append(entry)
    atomic_json_write(log_path, existing)


def review_discovered_configs(project_dir: str = ".") -> Dict[str, Any]:
    """Scan, validate, and review discovered AI tool configurations.

    Feature flag: OMG_CONFIG_DISCOVERY_ENABLED (default: False)

    Returns:
        {
            "skipped": bool (if feature disabled),
            "reason": str (if skipped),
            "approved": list,
            "rejected": list,
            "warnings": list,
            "pending": list,
        }
    """
    # Check feature flag via lazy import
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        common_module = importlib.import_module("hooks._common")
    except ImportError:
        try:
            common_module = importlib.import_module("_common")
        except ImportError:
            common_module = None
    try:
        get_feature_flag = common_module.get_feature_flag if common_module is not None else None
        if get_feature_flag is None:
            raise AttributeError("get_feature_flag unavailable")
        enabled = get_feature_flag("CONFIG_DISCOVERY", default=False)
    except Exception:
        enabled = os.getenv("OMG_CONFIG_DISCOVERY_ENABLED", "false").lower() in ("1", "true", "yes")

    if not enabled:
        return {"skipped": True, "reason": "feature disabled"}

    # Lazy import config discovery from tools/
    try:
        from tools import config_discovery as config_discovery_module
    except ImportError:
        tools_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
        tools_dir = os.path.normpath(tools_dir)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        try:
            config_discovery_module = importlib.import_module("config_discovery")
        except ImportError:
            return {
                "skipped": True,
                "reason": "config_discovery module not available",
            }

    # Run discovery
    discovery_result = config_discovery_module.discover_configs(project_dir)
    discovered = discovery_result.get("discovered", [])

    approved: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    warnings: List[str] = []
    pending: List[Dict[str, Any]] = []

    for config in discovered:
        tool = config.get("tool", "unknown")
        paths = config.get("paths", [])
        readable = config.get("readable", False)
        size_bytes = config.get("size_bytes", 0)

        if not paths:
            continue

        # Use the first path for validation
        rel_path = paths[0]
        abs_path = os.path.join(project_dir, rel_path)

        # Read content for security validation
        content = ""
        if readable and os.path.isfile(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(256 * 1024)  # Read up to 256KB for analysis
            except (OSError, IOError):
                content = ""

        # Validate security
        validation = _validate_config_security(abs_path, content)
        entry = {
            "tool": tool,
            "path": rel_path,
            "format": config.get("format", "unknown"),
            "size_bytes": size_bytes,
            "validation": validation,
        }

        if not validation["safe"]:
            entry["reason"] = "; ".join(validation["issues"])
            rejected.append(entry)
            _log_config_import(rel_path, tool, approved=False, project_dir=project_dir)
        else:
            if validation["warnings"]:
                warnings.extend(validation["warnings"])
            approved.append(entry)
            _log_config_import(rel_path, tool, approved=True, project_dir=project_dir)

    return {
        "skipped": False,
        "approved": approved,
        "rejected": rejected,
        "warnings": warnings,
        "pending": pending,
        "scan_dir": discovery_result.get("scan_dir", project_dir),
        "timestamp": discovery_result.get("timestamp", datetime.now(timezone.utc).isoformat()),
    }


def _main() -> int:
    try:
        payload = json.load(__import__("sys").stdin)
    except Exception:
        return 0

    file_path = payload.get("file_path", "")
    old_config = payload.get("old_config")
    new_config = payload.get("new_config")

    if isinstance(old_config, str):
        old_config = _load_json_file(old_config)
    if isinstance(new_config, str):
        new_config = _load_json_file(new_config)

    review = review_config_change(file_path, old_config, new_config)
    __import__("json").dump(review, __import__("sys").stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
