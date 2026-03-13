"""Replayable incident pack generation."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_pack(project_dir: str, incident_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    rel_path = Path(".omg") / "incidents" / f"{incident_id}.json"
    path = Path(project_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["path"] = rel_path.as_posix()
    return payload


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower())
    normalized = normalized.strip("-")
    return normalized or "chaos"


def _to_blockers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    blockers: list[str] = []
    for item in value:
        cleaned = str(item).strip()
        if cleaned:
            blockers.append(cleaned)
    return blockers


def build_incident_pack(
    project_dir: str,
    *,
    title: str,
    failing_tests: list[str],
    logs: list[str],
    diff_summary: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    incident_id = f"incident-{uuid4().hex}"
    payload = {
        "schema": "IncidentReplayPack",
        "incident_id": incident_id,
        "title": title,
        "generated_at": _now(),
        "trace_id": trace_id or "",
        "failing_tests": failing_tests,
        "logs": logs,
        "diff_summary": diff_summary,
        "reproduction_steps": [
            "Replay the failing tests.",
            "Inspect the attached logs.",
            "Validate the diff summary before patching.",
        ],
        "regression_guards": failing_tests,
    }

    return _write_pack(project_dir, incident_id, payload)


def build_worker_lifecycle_pack(
    project_dir: str,
    *,
    run_id: str,
    event: str,
    heartbeat: dict[str, Any] | None = None,
    termination: dict[str, Any] | None = None,
    cleanup: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    incident_id = f"worker-lifecycle-{uuid4().hex[:12]}"
    payload: dict[str, Any] = {
        "schema": "WorkerLifecycleReplayPack",
        "incident_id": incident_id,
        "run_id": run_id,
        "event": event,
        "generated_at": _now(),
        "trace_id": trace_id or "",
        "heartbeat": heartbeat or {},
        "termination": termination or {},
        "cleanup": cleanup or {},
        "reproduction_steps": [
            f"Review heartbeat state for run_id={run_id}.",
            f"Inspect worker lifecycle event: {event}.",
            "Check .omg/evidence/subagents/ for replay evidence.",
        ],
    }

    return _write_pack(project_dir, incident_id, payload)


def build_chaos_replay_pack(
    project_dir: str,
    *,
    run_id: str,
    scenario: str,
    fixture: str,
    fault: str,
    expected_outcome: dict[str, Any],
    observed: dict[str, Any],
    blockers: list[str] | None = None,
    trace_id: str | None = None,
    deterministic_seed: str | None = None,
    evidence_freshness_max_age_seconds: float | None = None,
) -> dict[str, Any]:
    scenario_slug = _slug(scenario)
    incident_id = f"chaos-{scenario_slug}-{uuid4().hex[:12]}"
    expected_blockers = _to_blockers(expected_outcome.get("blockers"))
    observed_blockers = _to_blockers(observed.get("blockers"))
    generated_at = _now()

    evidence_freshness: dict[str, Any] = {
        "generated_at": generated_at,
        "fixture_id": fixture,
        "trace_id": trace_id or "",
    }
    if evidence_freshness_max_age_seconds is not None:
        evidence_freshness["max_age_seconds"] = evidence_freshness_max_age_seconds

    payload: dict[str, Any] = {
        "schema": "ChaosReplayPack",
        "incident_id": incident_id,
        "run_id": run_id,
        "scenario": scenario,
        "fixture": fixture,
        "fault": fault,
        "generated_at": generated_at,
        "trace_id": trace_id or "",
        "deterministic_seed": deterministic_seed or "",
        "expected_outcome": expected_outcome,
        "observed": observed,
        "blockers": blockers or expected_blockers or observed_blockers,
        "evidence_freshness": evidence_freshness,
        "reproduction_steps": [
            f"Load fixture '{fixture}' and inject fault '{fault}'.",
            "Execute the deterministic chaos scenario with bounded timeout.",
            "Replay this pack and verify the blocker status reproduces.",
        ],
    }
    return _write_pack(project_dir, incident_id, payload)


def replay_chaos_pack(project_dir: str, pack_path: str) -> dict[str, Any]:
    root = Path(project_dir)
    source_path = Path(pack_path)
    if not source_path.is_absolute():
        source_path = root / source_path

    if not source_path.exists():
        return {
            "schema": "ChaosReplayResult",
            "status": "error",
            "reproduced": False,
            "reason": "pack_not_found",
            "pack_path": str(pack_path),
        }

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema": "ChaosReplayResult",
            "status": "error",
            "reproduced": False,
            "reason": "pack_unreadable",
            "pack_path": str(pack_path),
        }

    if not isinstance(payload, dict) or payload.get("schema") != "ChaosReplayPack":
        return {
            "schema": "ChaosReplayResult",
            "status": "error",
            "reproduced": False,
            "reason": "invalid_pack_schema",
            "pack_path": str(pack_path),
        }

    expected = payload.get("expected_outcome")
    observed = payload.get("observed")
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        return {
            "schema": "ChaosReplayResult",
            "status": "error",
            "reproduced": False,
            "reason": "missing_outcomes",
            "pack_path": str(source_path.relative_to(root)).replace("\\", "/"),
        }

    expected_status = str(expected.get("status", "")).strip().lower()
    observed_status = str(observed.get("status", "")).strip().lower()
    expected_blockers = set(_to_blockers(expected.get("blockers")))
    observed_blockers = set(_to_blockers(observed.get("blockers")))
    status_match = not expected_status or expected_status == observed_status
    blocker_match = expected_blockers.issubset(observed_blockers)
    reproduced = status_match and blocker_match

    return {
        "schema": "ChaosReplayResult",
        "status": "blocked" if reproduced and observed_status == "blocked" else ("ok" if reproduced else "mismatch"),
        "reproduced": reproduced,
        "run_id": str(payload.get("run_id", "")).strip(),
        "scenario": str(payload.get("scenario", "")).strip(),
        "pack_path": str(source_path.relative_to(root)).replace("\\", "/"),
        "expected_status": expected_status,
        "observed_status": observed_status,
        "expected_blockers": sorted(expected_blockers),
        "observed_blockers": sorted(observed_blockers),
    }


def collect_incident_signals(project_dir: str, run_id: str) -> dict[str, object]:
    root = Path(project_dir)
    incident_dir = root / ".omg" / "incidents"
    ledger_path = root / ".omg" / "state" / "ledger" / "tool-ledger.jsonl"

    incident_count = 0
    issue_payloads: list[dict[str, object]] = []
    if incident_dir.is_dir():
        for path in sorted(incident_dir.glob("*.json")):
            incident_count += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            title = str(payload.get("title") or payload.get("event") or payload.get("scenario") or "incident")
            issue_payloads.append(
                {
                    "severity": "low",
                    "surface": "hooks",
                    "title": f"Incident replay artifact present: {title}",
                    "description": "Incident artifact available for replay and triage verification.",
                    "fix_guidance": "Link this artifact to issue remediation if related to current run.",
                    "evidence_links": [str(path.relative_to(root)).replace("\\", "/")],
                    "approval_required": False,
                    "approval_reason": "",
                }
            )

    hook_issues: list[dict[str, object]] = list(issue_payloads)
    governed_tool_issues: list[dict[str, object]] = []
    if ledger_path.exists():
        try:
            with ledger_path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    entry_run_id = str(entry.get("run_id", "")).strip()
                    if run_id and entry_run_id and entry_run_id != run_id:
                        continue
                    lane = str(entry.get("lane", "")).strip()
                    governed_tool = str(entry.get("governed_tool", "")).strip()
                    if lane or governed_tool:
                        evidence = str(entry.get("evidence_path", "")).strip()
                        if not evidence:
                            governed_tool_issues.append(
                                {
                                    "severity": "high",
                                    "surface": "governed_tools",
                                    "title": "Governed tool execution missing evidence link",
                                    "description": (
                                        f"Governed tool '{governed_tool or entry.get('tool', '')}' ran on lane '{lane}' without evidence_path."
                                    ),
                                    "fix_guidance": "Attach signed evidence artifacts before approving governed tool output.",
                                    "evidence_links": [".omg/state/ledger/tool-ledger.jsonl"],
                                    "approval_required": True,
                                    "approval_reason": "signed approval required when governed tools lack evidence linkage",
                                }
                            )
                    exit_code = entry.get("exit_code")
                    if isinstance(exit_code, int) and exit_code != 0:
                        hook_issues.append(
                            {
                                "severity": "medium",
                                "surface": "hooks",
                                "title": "Hook/tool execution returned non-zero exit",
                                "description": f"Tool '{entry.get('tool', '')}' exited with code {exit_code}.",
                                "fix_guidance": "Inspect the tool ledger entry and replay with bounded diagnostics.",
                                "evidence_links": [".omg/state/ledger/tool-ledger.jsonl"],
                                "approval_required": False,
                                "approval_reason": "",
                            }
                        )
        except OSError:
            pass

    return {
        "incident_count": incident_count,
        "hook_issues": hook_issues,
        "governed_tool_issues": governed_tool_issues,
    }
