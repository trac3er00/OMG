#!/usr/bin/env python3
"""OAL v1 Trust Review

Analyzes high-risk configuration changes (hooks/MCP/env/permissions) and emits
structured trust review artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any


DANGEROUS_IN_ALLOW = [
    "Bash(rm:*)", "Bash(sudo:*)", "Bash(curl:*)", "Bash(wget:*)",
    "Bash(ssh:*)", "Bash(nc:*)", "Bash(ncat:*)",
]


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

    for dangerous in DANGEROUS_IN_ALLOW:
        if dangerous in added_allow:
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
    trust_dir = os.path.join(project_dir, ".oal", "trust")
    os.makedirs(trust_dir, exist_ok=True)
    manifest_path = os.path.join(trust_dir, "manifest.lock.json")

    payload = {
        "version": "oal-v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_review": review,
    }
    digest_input = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["signature"] = hashlib.sha256(digest_input).hexdigest()

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)

    return manifest_path


def _load_json_file(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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
