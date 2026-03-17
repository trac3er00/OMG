from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, cast

from runtime import plugin_interop


def _load_allowlist(root: str | None) -> list[plugin_interop.PluginAllowlistEntry]:
    load_fn = cast(
        Callable[[str | None], list[plugin_interop.PluginAllowlistEntry]] | None,
        getattr(plugin_interop, "load_plugin_allowlist", None),
    )
    if callable(load_fn):
        return load_fn(root)
    return []


_LIVE_BUDGET_MS: float = 3000.0


def _resolve_mcp_command(server_name: str, root: str | None) -> list[str] | None:
    root_path = Path(root or ".").resolve()
    for mcp_path in (
        root_path / ".claude-plugin" / "mcp.json",
        root_path / ".mcp.json",
    ):
        try:
            raw = mcp_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        servers = payload.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue
        entry = servers.get(server_name)
        if not isinstance(entry, dict):
            continue
        cmd = entry.get("command")
        args = entry.get("args", [])
        if isinstance(cmd, str):
            cmd_list = [cmd]
            if isinstance(args, list):
                cmd_list.extend(str(a) for a in args)
            return cmd_list
    return None


def _probe_mcp_servers_live(
    records: list[plugin_interop.PluginInteropRecord],
    root: str | None,
) -> list[dict[str, object]]:
    budget_start = time.monotonic()
    results: list[dict[str, object]] = []
    seen: set[str] = set()

    for record in records:
        for server_name in record.mcp_servers:
            if server_name in seen:
                continue
            seen.add(server_name)

            elapsed_total_ms = (time.monotonic() - budget_start) * 1000.0
            if elapsed_total_ms >= _LIVE_BUDGET_MS:
                results.append({
                    "server": server_name,
                    "status": "skipped",
                    "elapsed_ms": 0.0,
                })
                continue

            command = _resolve_mcp_command(server_name, root)
            if command is None:
                results.append({
                    "server": server_name,
                    "status": "skipped",
                    "elapsed_ms": 0.0,
                })
                continue

            remaining_ms = _LIVE_BUDGET_MS - elapsed_total_ms
            probe_timeout = min(1500, int(remaining_ms))
            results.append(
                plugin_interop.probe_mcp_server_live(
                    server_name, command, timeout_ms=probe_timeout,
                )
            )

    return results


def _record_sort_key(record: plugin_interop.PluginInteropRecord) -> tuple[str, str, str, str]:
    return (record.host, record.plugin_id, record.layer, record.source)


def _load_mcp_servers_from_configs(root_path: Path) -> list[tuple[str, str]]:
    """Return deduplicated ``(mcp:<name>, host)`` pairs from project MCP configs.

    Reads ``.mcp.json`` and ``.claude-plugin/mcp.json`` — both are
    project-scoped and implicitly target the ``claude`` host.
    """
    checked: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for mcp_path in (
        root_path / ".mcp.json",
        root_path / ".claude-plugin" / "mcp.json",
    ):
        try:
            raw = mcp_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        servers = payload.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue
        for name in servers:
            pair = (f"mcp:{name}", "claude")
            if pair not in seen:
                seen.add(pair)
                checked.append(pair)
    return checked


def check_allowlist_completeness(root: str | None = None) -> dict[str, object]:
    """Compare configured OMG MCP sources against approved allowlist entries.

    Only OMG-managed MCP sources (declared in project-level configs) are
    checked.  Discoverable-only resources that were never previously approved
    are not flagged as errors.
    """
    approvals = _load_allowlist(root)
    approved_set: set[tuple[str, str]] = {(e.source, e.host) for e in approvals}
    root_path = Path(root or ".").resolve()
    checked_sources = _load_mcp_servers_from_configs(root_path)

    missing: list[str] = []
    for source, host in checked_sources:
        if (source, host) not in approved_set:
            missing.append(f"{source}@{host}")

    return {
        "complete": len(missing) == 0,
        "missing_approvals": missing,
        "allowlisted_count": len(approvals),
        "checked_count": len(checked_sources),
    }


def run_plugin_diagnostics(root: str | None = None, live: bool = False) -> dict[str, object]:
    started = time.monotonic()

    omg_payload = plugin_interop.discover_omg_plugin_state(root)
    host_payload = plugin_interop.discover_host_plugin_state(root)

    all_records = [*omg_payload.records, *host_payload.records]
    ordered_records = sorted(all_records, key=_record_sort_key)
    conflicts = plugin_interop.classify_conflicts(ordered_records)
    approvals = _load_allowlist(root)
    approval_states = plugin_interop.get_approval_status_for_all(ordered_records, approvals)

    blocker_count = sum(1 for conflict in conflicts if conflict.severity == "blocker")
    warning_count = sum(1 for conflict in conflicts if conflict.severity == "warning")
    info_count = sum(1 for conflict in conflicts if conflict.severity == "info")

    if blocker_count > 0:
        status = "error"
    elif warning_count > 0:
        status = "warn"
    else:
        status = "ok"

    next_actions: list[str] = []
    for conflict in conflicts:
        action = conflict.next_action
        if action and action not in next_actions:
            next_actions.append(action)
        if len(next_actions) >= 3:
            break

    result: dict[str, object] = {
        "schema": "PluginDiagnosticsResult",
        "status": status,
        "records": [record.to_dict() for record in ordered_records],
        "conflicts": [
            {
                "code": conflict.code,
                "severity": conflict.severity,
                "affected_plugin_ids": list(conflict.affected_plugin_ids),
                "affected_hosts": list(conflict.affected_hosts),
                "detail": conflict.detail,
                "next_action": conflict.next_action,
            }
            for conflict in conflicts
        ],
        "approval_states": dict(sorted(approval_states.items())),
        "summary": {
            "total_records": len(ordered_records),
            "total_conflicts": len(conflicts),
            "blockers": blocker_count,
            "warnings": warning_count,
            "infos": info_count,
        },
        "next_actions": next_actions,
        "elapsed_ms": (time.monotonic() - started) * 1000.0,
    }

    result["allowlist_completeness"] = check_allowlist_completeness(root)

    if live:
        result["live_probe_results"] = _probe_mcp_servers_live(ordered_records, root)

    return result


def _infer_resource_type(source: str) -> str:
    if source.startswith("mcp:"):
        return "mcp_server"
    if source.startswith("skill:"):
        return "skill"
    if source.startswith("plugin:"):
        return "plugin"
    raise ValueError("source must start with one of: mcp:, skill:, plugin:")


def _record_sources(record: dict[str, object]) -> set[str]:
    discovered: set[str] = set()
    for server in cast(list[object], record.get("mcp_servers", [])):
        if isinstance(server, str):
            discovered.add(f"mcp:{server}")

    plugin_id = record.get("plugin_id")
    source = record.get("source")
    if isinstance(plugin_id, str):
        if source == plugin_interop.Source.SKILL_REGISTRY.value:
            discovered.add(f"skill:{plugin_id}")
        else:
            discovered.add(f"plugin:{plugin_id}")
    return discovered


def approve_plugin(source: str, host: str, reason: str, root: str | None = None) -> dict[str, object]:
    diagnostics = run_plugin_diagnostics(root)
    records = diagnostics.get("records", [])
    approval_states = diagnostics.get("approval_states", {})

    matching_discovered = False
    if isinstance(records, list):
        for record in cast(list[object], records):
            if not isinstance(record, dict):
                continue
            record_host = cast(str | None, record.get("host"))
            if record_host != host:
                continue
            if source in _record_sources(cast(dict[str, object], record)):
                matching_discovered = True
                break

    if not matching_discovered and isinstance(approval_states, dict):
        for plugin_id, _status in cast(dict[object, object], approval_states).items():
            if not isinstance(plugin_id, str):
                continue
            if source in {f"plugin:{plugin_id}", f"skill:{plugin_id}"}:
                matching_discovered = True
                break

    if not matching_discovered:
        return {
            "schema": "ApprovalResult",
            "status": "error",
            "message": (
                f"No discovered resource matching source={source!r} and host={host!r}. "
                "Run diagnose-plugins first."
            ),
        }

    entry = plugin_interop.PluginAllowlistEntry(
        source=source,
        host=host,
        resource_type=_infer_resource_type(source),
        reason=reason,
    )
    plugin_interop.validate_plugin_allowlist_entry(entry.to_dict())
    entries = plugin_interop.load_plugin_allowlist(root)

    exists = any(existing.source == source and existing.host == host for existing in entries)
    if not exists:
        entries.append(entry)

    _ = plugin_interop.save_plugin_allowlist(entries, root)
    return {
        "schema": "ApprovalResult",
        "status": "ok",
        "source": source,
        "host": host,
        "message": "Approved and saved to .omg/state/plugins-allowlist.yaml",
    }
