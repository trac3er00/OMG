from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import cast

from runtime.forge_agents import collect_forge_evidence_issues
from runtime.incident_replay import collect_incident_signals
from runtime.plugin_diagnostics import run_plugin_diagnostics
from runtime.plugin_interop import conflict_severity_to_issue_severity
from runtime.session_health import collect_session_health_risks
from tools.session_snapshot import collect_snapshot_signals


_ALL_SURFACES: tuple[str, ...] = (
    "live_session",
    "forge_runs",
    "hooks",
    "skills",
    "mcps",
    "plugin_interop",
    "governed_tools",
    "domain_pipelines",
)

_SEVERITY_RANK: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


@dataclass(slots=True)
class Issue:
    id: str
    severity: str
    surface: str
    title: str
    description: str
    fix_guidance: str
    evidence_links: list[str]
    approval_required: bool
    approval_reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class IssueReport:
    run_id: str
    timestamp: str
    issues: list[Issue]
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "IssueReport",
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": dict(self.summary),
        }


class IssueSurface:
    def __init__(self, project_dir: str | None = None) -> None:
        self.project_dir: str = str(Path(project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve())

    def scan(self, run_id: str, surfaces: list[str] | tuple[str, ...] | None = None) -> IssueReport:
        selected_surfaces = self._normalize_surfaces(surfaces)
        issues: list[Issue] = []
        scan_map = {
            "live_session": self._scan_live_session,
            "forge_runs": self._scan_forge_runs,
            "hooks": self._scan_hooks,
            "skills": self._scan_skills,
            "mcps": self._scan_mcps,
            "plugin_interop": self._scan_plugin_interop,
            "governed_tools": self._scan_governed_tools,
            "domain_pipelines": self._scan_domain_pipelines,
        }

        for surface in selected_surfaces:
            scanner = scan_map.get(surface)
            if scanner is not None:
                issues.extend(scanner(run_id))

        ranked_issues = sorted(
            issues,
            key=lambda issue: (
                _SEVERITY_RANK.get(issue.severity, 99),
                issue.surface,
                issue.id,
            ),
        )
        summary = self._build_summary(ranked_issues, selected_surfaces)
        report = IssueReport(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            issues=ranked_issues,
            summary=summary,
        )
        report_path = self.emit_report(run_id, report)
        report.summary["report_path"] = report_path
        return report

    def simulate_failure(self, surface: str, scenario: str) -> dict[str, object]:
        normalized_surface = str(surface).strip().lower() or "unknown"
        normalized_scenario = str(scenario).strip().lower() or "unknown"
        dangerous_probe = any(
            token in normalized_scenario
            for token in ("delete", "overwrite", "rm -rf", "exfiltrate", "credential", "chmod")
        )
        severity = "high" if dangerous_probe else "medium"
        approval_required = dangerous_probe
        issue = Issue(
            id=f"sim-{normalized_surface}-{abs(hash(normalized_scenario)) % 100000}",
            severity=severity,
            surface=normalized_surface,
            title="Sandboxed red-team simulation result",
            description=(
                "Probe classified as potentially destructive and blocked in simulation mode."
                if dangerous_probe
                else "Probe classified as non-destructive simulation scenario."
            ),
            fix_guidance=(
                "Keep simulation read-only; require signed approval artifact before any real mutation workflow."
                if dangerous_probe
                else "Document scenario and add replay fixture for continued diagnostics."
            ),
            evidence_links=[f"sim://{normalized_surface}/{normalized_scenario}"],
            approval_required=approval_required,
            approval_reason=(
                "signed approval required before leaving read-only simulation mode"
                if dangerous_probe
                else ""
            ),
        )
        return {
            "schema": "IssueSimulationResult",
            "surface": normalized_surface,
            "scenario": normalized_scenario,
            "mutated": False,
            "issue": issue.to_dict(),
        }

    def emit_report(self, run_id: str, report: IssueReport) -> str:
        evidence_dir = Path(self.project_dir) / ".omg" / "evidence" / "issues"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"{run_id}.json"
        tmp_path = path.with_name(f"{path.name}.tmp")
        _ = tmp_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)
        return str(path.relative_to(self.project_dir)).replace("\\", "/")

    def _normalize_surfaces(self, surfaces: list[str] | tuple[str, ...] | None) -> list[str]:
        if not surfaces:
            return list(_ALL_SURFACES)
        normalized: list[str] = []
        for item in surfaces:
            candidate = str(item).strip().lower()
            if candidate in _ALL_SURFACES and candidate not in normalized:
                normalized.append(candidate)
        return normalized or list(_ALL_SURFACES)

    def _build_summary(self, issues: list[Issue], surfaces: list[str]) -> dict[str, object]:
        by_severity = {name: 0 for name in _SEVERITY_RANK}
        by_surface = {surface: 0 for surface in surfaces}
        for issue in issues:
            if issue.severity in by_severity:
                by_severity[issue.severity] += 1
            by_surface[issue.surface] = by_surface.get(issue.surface, 0) + 1
        return {
            "total": len(issues),
            "surfaces_scanned": surfaces,
            "by_severity": by_severity,
            "by_surface": by_surface,
            "requires_signed_approval": any(issue.approval_required for issue in issues),
        }

    def _issue_from_payload(self, run_id: str, idx: int, payload: dict[str, object]) -> Issue:
        severity = str(payload.get("severity", "info"))
        approval_required = bool(payload.get("approval_required", severity in {"critical", "high"}))
        approval_reason = str(payload.get("approval_reason", "")).strip()
        if approval_required and not approval_reason:
            approval_reason = "signed approval required before fix execution"
        surface = str(payload.get("surface", "unknown"))
        return Issue(
            id=f"{run_id}-{surface}-{idx}",
            severity=severity,
            surface=surface,
            title=str(payload.get("title", "Issue detected")),
            description=str(payload.get("description", "")),
            fix_guidance=str(payload.get("fix_guidance", "")),
            evidence_links=self._to_str_list(payload.get("evidence_links")),
            approval_required=approval_required,
            approval_reason=approval_reason,
        )

    def _to_str_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in cast(list[object], value):
            text = str(item).strip()
            if text:
                result.append(text)
        return result

    def _scan_live_session(self, run_id: str) -> list[Issue]:
        payloads = collect_session_health_risks(self.project_dir, run_id)
        snapshots = collect_snapshot_signals(str(Path(self.project_dir) / ".omg" / "state"))
        issues = [self._issue_from_payload(run_id, idx, payload) for idx, payload in enumerate(payloads, start=1)]
        if int(snapshots.get("snapshot_count", 0)) == 0:
            issues.append(
                self._issue_from_payload(
                    run_id,
                    len(issues) + 1,
                    {
                        "severity": "low",
                        "surface": "live_session",
                        "title": "No session snapshots available",
                        "description": "Issue scan found no state snapshots for replay diagnostics.",
                        "fix_guidance": "Enable snapshot capture or run a snapshot before deep issue triage.",
                        "evidence_links": [".omg/state/snapshots/"],
                        "approval_required": False,
                        "approval_reason": "",
                    },
                )
            )
        return issues

    def _scan_forge_runs(self, run_id: str) -> list[Issue]:
        payloads = collect_forge_evidence_issues(self.project_dir, run_id)
        return [self._issue_from_payload(run_id, idx, payload) for idx, payload in enumerate(payloads, start=1)]

    def _scan_hooks(self, run_id: str) -> list[Issue]:
        signals = collect_incident_signals(self.project_dir, run_id)
        payloads = signals.get("hook_issues", [])
        if not isinstance(payloads, list):
            return []
        typed_payloads = [payload for payload in payloads if isinstance(payload, dict)]
        return [
            self._issue_from_payload(run_id, idx, payload)
            for idx, payload in enumerate(typed_payloads, start=1)
        ]

    def _scan_skills(self, run_id: str) -> list[Issue]:
        diagnostics = run_plugin_diagnostics(root=self.project_dir, live=False)
        records = diagnostics.get("records", [])
        if not isinstance(records, list):
            return []
        typed_records = [record for record in records if isinstance(record, dict)]
        skill_records = [record for record in typed_records if record.get("source") == "skill_registry"]
        if skill_records:
            return []
        return [
            self._issue_from_payload(
                run_id,
                1,
                {
                    "severity": "medium",
                    "surface": "skills",
                    "title": "No compiled skills discovered",
                    "description": "Diagnostic scan did not detect skill-registry entries for the active workspace.",
                    "fix_guidance": "Regenerate skill registry artifacts and verify .omg/state/skill_registry/compact.json.",
                    "evidence_links": [".omg/state/skill_registry/compact.json"],
                    "approval_required": False,
                    "approval_reason": "",
                },
            )
        ]

    def _scan_mcps(self, run_id: str) -> list[Issue]:
        diagnostics = run_plugin_diagnostics(root=self.project_dir, live=False)
        records = diagnostics.get("records", [])
        if not isinstance(records, list):
            return []
        typed_records = [record for record in records if isinstance(record, dict)]
        mcp_records = [record for record in typed_records if record.get("mcp_servers")]
        if mcp_records:
            return []
        return [
            self._issue_from_payload(
                run_id,
                1,
                {
                    "severity": "medium",
                    "surface": "mcps",
                    "title": "No MCP servers discovered",
                    "description": "Issue scan found no configured MCP servers across discovered host configs.",
                    "fix_guidance": "Register required MCP servers and rerun diagnostics.",
                    "evidence_links": [".mcp.json", ".claude-plugin/mcp.json"],
                    "approval_required": False,
                    "approval_reason": "",
                },
            )
        ]

    def _scan_plugin_interop(self, run_id: str) -> list[Issue]:
        diagnostics = run_plugin_diagnostics(root=self.project_dir, live=False)
        conflicts = diagnostics.get("conflicts", [])
        if not isinstance(conflicts, list):
            return []

        issues: list[Issue] = []
        typed_conflicts = [conflict for conflict in conflicts if isinstance(conflict, dict)]
        for idx, conflict in enumerate(typed_conflicts, start=1):
            severity = conflict_severity_to_issue_severity(str(conflict.get("severity", "info")))
            code = str(conflict.get("code", "conflict"))
            detail = str(conflict.get("detail", ""))
            fix_guidance = str(conflict.get("next_action", ""))
            approval_required = severity in {"critical", "high"}
            issues.append(
                self._issue_from_payload(
                    run_id,
                    idx,
                    {
                        "severity": severity,
                        "surface": "plugin_interop",
                        "title": f"Plugin interop conflict: {code}",
                        "description": detail,
                        "fix_guidance": fix_guidance,
                        "evidence_links": [".omg/state/plugins-allowlist.yaml", ".mcp.json"],
                        "approval_required": approval_required,
                        "approval_reason": (
                            "signed approval required to modify plugin ownership on blocker/high conflicts"
                            if approval_required
                            else ""
                        ),
                    },
                )
            )
        return issues

    def _scan_governed_tools(self, run_id: str) -> list[Issue]:
        signals = collect_incident_signals(self.project_dir, run_id)
        payloads = signals.get("governed_tool_issues", [])
        if not isinstance(payloads, list):
            return []
        typed_payloads = [payload for payload in payloads if isinstance(payload, dict)]
        return [
            self._issue_from_payload(run_id, idx, payload)
            for idx, payload in enumerate(typed_payloads, start=1)
        ]

    def _scan_domain_pipelines(self, run_id: str) -> list[Issue]:
        payloads = collect_forge_evidence_issues(self.project_dir, run_id, domain_pipeline_only=True)
        return [self._issue_from_payload(run_id, idx, payload) for idx, payload in enumerate(payloads, start=1)]


__all__ = [
    "Issue",
    "IssueReport",
    "IssueSurface",
]
