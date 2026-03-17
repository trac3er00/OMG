from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import cast

from runtime.issue_surface import Issue, IssueReport, IssueSurface, prune_operational_evidence
import scripts.omg as omg_cli


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_issue_surface_finds_seeded_conflict_and_missing_evidence(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "plugins" / "alpha" / "plugin.json",
        {
            "name": "alpha",
            "commands": {
                "/OMG:collision": {"description": "alpha command"},
            },
        },
    )
    _write_json(
        tmp_path / "plugins" / "beta" / "plugin.json",
        {
            "name": "beta",
            "commands": {
                "/OMG:collision": {"description": "beta command"},
            },
        },
    )
    _write_json(
        tmp_path / ".omg" / "evidence" / "forge-specialists-seeded.json",
        {
            "status": "ok",
            "domain": "vision",
            "artifact_contracts": {
                "model_card": {
                    "status": "pending_verification",
                    "reason": "missing model card",
                }
            },
        },
    )
    (tmp_path / ".omg" / "state" / "ledger").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omg" / "state" / "ledger" / "tool-ledger.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-03-13T00:00:00+00:00",
                "tool": "Bash",
                "lane": "terminal-lane",
                "governed_tool": "Bash",
                "run_id": "seeded-run",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    surface = IssueSurface(project_dir=str(tmp_path))
    report = surface.scan("seeded-run")

    assert report.summary["total"]
    assert any(issue.surface == "plugin_interop" for issue in report.issues)
    assert any(issue.surface in {"forge_runs", "domain_pipelines"} for issue in report.issues)
    assert any(issue.approval_required for issue in report.issues)
    assert all(issue.fix_guidance for issue in report.issues)
    assert all(issue.evidence_links for issue in report.issues)

    report_path = tmp_path / ".omg" / "evidence" / "issues" / "seeded-run.json"
    assert report_path.exists()


def test_dangerous_probe_simulation_is_non_mutating(tmp_path: Path) -> None:
    protected = tmp_path / "protected.txt"
    protected.write_text("do-not-touch\n", encoding="utf-8")

    surface = IssueSurface(project_dir=str(tmp_path))
    result = surface.simulate_failure("hooks", "delete protected lock")

    assert result["mutated"] is False
    assert json.loads(json.dumps(result))["issue"]["approval_required"] is True
    assert protected.read_text(encoding="utf-8") == "do-not-touch\n"


def test_issue_report_includes_required_fields() -> None:
    issue = Issue(
        id="id-1",
        severity="high",
        surface="plugin_interop",
        title="collision",
        description="conflict",
        fix_guidance="rename one command",
        evidence_links=[".omg/state/ledger/tool-ledger.jsonl"],
        approval_required=True,
        approval_reason="signed approval required",
    )
    report = IssueReport(
        run_id="run-1",
        timestamp="2026-03-13T00:00:00+00:00",
        issues=[issue],
        summary={"total": 1},
    )

    payload = report.to_dict()
    issue_payload = cast(list[dict[str, object]], payload["issues"])[0]
    assert issue_payload["severity"] == "high"
    assert issue_payload["fix_guidance"] == "rename one command"
    assert issue_payload["evidence_links"]
    assert issue_payload["approval_required"] is True
    assert issue_payload["approval_reason"]


def test_fix_and_issue_commands_share_backend_without_role_collision(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    scan_calls: list[dict[str, object]] = []

    class FakeIssueSurface:
        def __init__(self, project_dir: str | None = None) -> None:
            self.project_dir = project_dir

        def scan(self, run_id: str, surfaces: list[str] | None = None) -> IssueReport:
            scan_calls.append({"run_id": run_id, "surfaces": list(surfaces or [])})
            return IssueReport(
                run_id=run_id,
                timestamp="2026-03-13T00:00:00+00:00",
                issues=[],
                summary={"total": 0, "report_path": f".omg/evidence/issues/{run_id}.json"},
            )

        def simulate_failure(self, surface: str, scenario: str) -> dict[str, object]:
            return {
                "schema": "IssueSimulationResult",
                "surface": surface,
                "scenario": scenario,
                "mutated": False,
                "issue": {},
            }

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(omg_cli, "IssueSurface", FakeIssueSurface)
    monkeypatch.setattr(omg_cli, "dispatch_runtime", lambda runtime, payload: {"status": "ok", "runtime": runtime, "goal": payload["goal"]})

    assert omg_cli.cmd_fix(argparse.Namespace(issue="INC-42", runtime="claude")) == 0
    fix_output = json.loads(capsys.readouterr().out)
    assert "issue_surface" in fix_output
    assert fix_output["goal"] == "Fix issue INC-42"

    assert (
        omg_cli.cmd_issue(
            argparse.Namespace(
                run_id="diag-1",
                surfaces="",
                simulate_surface="",
                simulate_scenario="",
            )
        )
        == 0
    )
    issue_output = json.loads(capsys.readouterr().out)
    assert issue_output["schema"] == "IssueCommandResult"
    assert "issue_surface" not in issue_output
    assert len(scan_calls) == 2


def test_issue_surface_reports_evidence_retention_thresholds(tmp_path: Path) -> None:
    evidence_dir = tmp_path / ".omg" / "evidence"
    heartbeat_dir = tmp_path / ".omg" / "state" / "worker-heartbeats"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(101):
        _ = (evidence_dir / f"forge-{idx}.json").write_text("{}\n", encoding="utf-8")
    for idx in range(21):
        _ = (heartbeat_dir / f"heartbeat-{idx}.json").write_text("{}\n", encoding="utf-8")

    report = IssueSurface(project_dir=str(tmp_path)).scan("retention-run", surfaces=["governed_tools"])

    retention_issues = [
        issue
        for issue in report.issues
        if issue.title in {"Operational evidence retention exceeded", "Worker heartbeat residue exceeded"}
    ]
    assert len(retention_issues) == 2
    assert all(issue.severity == "medium" for issue in retention_issues)


def test_prune_operational_evidence_respects_exemptions_and_age(tmp_path: Path) -> None:
    evidence_dir = tmp_path / ".omg" / "evidence"
    issues_dir = evidence_dir / "issues"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    issues_dir.mkdir(parents=True, exist_ok=True)

    old_paths = [
        evidence_dir / "forge-old.json",
        evidence_dir / "worker-replay-old.json",
        evidence_dir / "trust-old.json",
        evidence_dir / "approval-old.json",
        evidence_dir / "security-old.json",
        evidence_dir / "sbom-old.json",
        evidence_dir / "license-old.json",
    ]
    fresh_path = evidence_dir / "forge-fresh.json"

    for path in old_paths:
        _ = path.write_text("{}\n", encoding="utf-8")
    _ = fresh_path.write_text("{}\n", encoding="utf-8")
    _ = (issues_dir / "kept.json").write_text("{}\n", encoding="utf-8")

    stale_time = time.time() - (10 * 86400)
    for path in old_paths:
        os.utime(path, (stale_time, stale_time))

    dry_run_result = prune_operational_evidence(str(tmp_path), max_age_days=7, dry_run=True)
    assert dry_run_result == {"pruned": 2, "preserved": 7, "dry_run": True}
    assert (evidence_dir / "forge-old.json").exists()
    assert (evidence_dir / "worker-replay-old.json").exists()

    result = prune_operational_evidence(str(tmp_path), max_age_days=7, dry_run=False)
    assert result == {"pruned": 2, "preserved": 7, "dry_run": False}
    assert not (evidence_dir / "forge-old.json").exists()
    assert not (evidence_dir / "worker-replay-old.json").exists()
    assert (evidence_dir / "trust-old.json").exists()
    assert (evidence_dir / "approval-old.json").exists()
    assert (evidence_dir / "security-old.json").exists()
    assert (evidence_dir / "sbom-old.json").exists()
    assert (evidence_dir / "license-old.json").exists()
    assert (evidence_dir / "forge-fresh.json").exists()
    assert (evidence_dir / "issues").is_dir()
