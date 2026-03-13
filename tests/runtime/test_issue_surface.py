from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from runtime.issue_surface import Issue, IssueReport, IssueSurface
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
