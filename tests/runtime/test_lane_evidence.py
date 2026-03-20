"""Tests for NF4b (lane evidence collection) and NF4c (lane rendering)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.proof_gate import collect_lane_evidence, detect_lane, render_lane_status


class TestDetectLane:
    """Tests for detect_lane auto-detection."""

    def test_detect_lane_fix_commits_with_test_files_returns_bug_fix(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["fix: resolve null pointer issue"],
            files=["test_utils.py", "utils.py"],
        )
        assert result == "lane-bug-fix"

    def test_detect_lane_bug_keyword_with_test_files_returns_bug_fix(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["bug: handle edge case in parser"],
            files=["parser_test.go", "parser.go"],
        )
        assert result == "lane-bug-fix"

    def test_detect_lane_sarif_file_returns_security_remediation(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            files=["results.sarif", "src/main.py"],
        )
        assert result == "lane-security-remediation"

    def test_detect_lane_security_commit_returns_security_remediation(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["security: patch XSS vulnerability"],
        )
        assert result == "lane-security-remediation"

    def test_detect_lane_cve_commit_returns_security_remediation(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["patch CVE-2024-1234"],
        )
        assert result == "lane-security-remediation"

    def test_detect_lane_vuln_commit_returns_security_remediation(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["fix vulnerability in auth module"],
        )
        assert result == "lane-security-remediation"

    def test_detect_lane_migration_file_returns_migration_refactor(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            files=["migrations/001_initial.py", "models.py"],
        )
        assert result == "lane-migration-refactor"

    def test_detect_lane_dockerfile_returns_migration_refactor(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            files=["Dockerfile", "docker-compose.yml"],
        )
        assert result == "lane-migration-refactor"

    def test_detect_lane_migrate_commit_returns_migration_refactor(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["migrate database schema to v2"],
        )
        assert result == "lane-migration-refactor"

    def test_detect_lane_upgrade_commit_returns_migration_refactor(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["upgrade dependencies to latest versions"],
        )
        assert result == "lane-migration-refactor"

    def test_detect_lane_regression_commit_returns_regression_recovery(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["regression: restore previous behavior"],
        )
        assert result == "lane-regression-recovery"

    def test_detect_lane_revert_commit_returns_regression_recovery(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["revert: undo breaking change from abc123"],
        )
        assert result == "lane-regression-recovery"

    def test_detect_lane_feature_label_returns_feature_ship(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            pr_labels=["feature", "enhancement"],
        )
        assert result == "lane-feature-ship"

    def test_detect_lane_default_returns_feature_ship(self) -> None:
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["add new endpoint"],
            files=["api.py"],
        )
        assert result == "lane-feature-ship"

    def test_detect_lane_empty_context_returns_feature_ship(self) -> None:
        result = detect_lane(project_dir="/tmp/project")
        assert result == "lane-feature-ship"

    def test_detect_lane_security_takes_precedence_over_fix(self) -> None:
        # Security keywords should take precedence over fix keywords
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["fix security vulnerability"],
            files=["test_auth.py"],
        )
        assert result == "lane-security-remediation"

    def test_detect_lane_regression_takes_highest_precedence(self) -> None:
        # Regression/revert should take highest precedence
        result = detect_lane(
            project_dir="/tmp/project",
            commit_messages=["revert security fix"],
            files=["results.sarif", "test_auth.py"],
        )
        assert result == "lane-regression-recovery"


class TestCollectLaneEvidence:
    """Tests for collect_lane_evidence."""

    def test_collect_lane_evidence_writes_evidence_file(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        lane_id = "lane-feature-ship"
        run_id = "run-123"

        result = collect_lane_evidence(project_dir, lane_id, run_id)

        # Verify evidence file was written
        evidence_file = tmp_path / ".omg" / "evidence" / f"lane-{lane_id}-{run_id}.json"
        assert evidence_file.exists()

        # Verify file content matches return value
        content = json.loads(evidence_file.read_text(encoding="utf-8"))
        assert content["lane"] == lane_id
        assert content["run_id"] == run_id
        assert content["schema"] == "LaneEvidence"

    def test_collect_lane_evidence_reports_missing_requirements(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        lane_id = "lane-feature-ship"
        run_id = "run-456"

        result = collect_lane_evidence(project_dir, lane_id, run_id)

        # Without any evidence files, all requirements should be missing
        assert result["lane"] == lane_id
        assert result["run_id"] == run_id
        assert len(result["missing"]) > 0
        assert len(result["met"]) == 0
        assert result["completeness"] == 0.0

    def test_collect_lane_evidence_detects_met_requirements(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        lane_id = "lane-bug-fix"
        run_id = "run-789"

        # Create evidence files
        evidence_dir = tmp_path / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "junit.xml").write_text("<testsuite/>", encoding="utf-8")
        (evidence_dir / "lsp-check.json").write_text('{"status": "ok"}', encoding="utf-8")

        result = collect_lane_evidence(project_dir, lane_id, run_id)

        assert "tests" in result["met"]
        assert "lsp_clean" in result["met"]
        assert result["completeness"] > 0.0

    def test_collect_lane_evidence_returns_correct_structure(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        lane_id = "lane-security-remediation"
        run_id = "run-sec-1"

        result = collect_lane_evidence(project_dir, lane_id, run_id)

        # Verify structure
        assert "schema" in result
        assert "lane" in result
        assert "lane_label" in result
        assert "gate_type" in result
        assert "run_id" in result
        assert "requirements" in result
        assert "met" in result
        assert "missing" in result
        assert "completeness" in result
        assert isinstance(result["requirements"], list)
        assert isinstance(result["met"], list)
        assert isinstance(result["missing"], list)
        assert isinstance(result["completeness"], float)

    def test_collect_lane_evidence_includes_lane_metadata(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        lane_id = "lane-bug-fix"
        run_id = "run-meta-1"

        result = collect_lane_evidence(project_dir, lane_id, run_id)

        assert result["lane_label"] == "Bug Fix"
        assert result["gate_type"] == "active-gated"

    def test_collect_lane_evidence_calculates_completeness(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        lane_id = "lane-bug-fix"  # Has 4 requirements
        run_id = "run-complete-1"

        # Create 2 of 4 evidence files
        evidence_dir = tmp_path / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "junit.xml").write_text("<testsuite/>", encoding="utf-8")
        (evidence_dir / "lsp-check.json").write_text('{"status": "ok"}', encoding="utf-8")

        result = collect_lane_evidence(project_dir, lane_id, run_id)

        # 2 of 4 requirements met = 50%
        assert result["completeness"] == 0.5


class TestRenderLaneStatus:
    """Tests for render_lane_status."""

    def test_render_lane_status_shows_lane_table(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        evidence_dir = tmp_path / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Create lane evidence files
        lane_data_1 = {
            "schema": "LaneEvidence",
            "lane": "lane-feature-ship",
            "lane_label": "Feature Ship",
            "gate_type": "active-gated",
            "run_id": "run-1",
            "completeness": 0.8,
        }
        lane_data_2 = {
            "schema": "LaneEvidence",
            "lane": "lane-bug-fix",
            "lane_label": "Bug Fix",
            "gate_type": "active-advisory",
            "run_id": "run-2",
            "completeness": 0.6,
        }

        (evidence_dir / "lane-lane-feature-ship-run-1.json").write_text(
            json.dumps(lane_data_1), encoding="utf-8"
        )
        (evidence_dir / "lane-lane-bug-fix-run-2.json").write_text(
            json.dumps(lane_data_2), encoding="utf-8"
        )

        result = render_lane_status(project_dir)

        # Verify table format
        assert "Lane" in result
        assert "Status" in result
        assert "Completeness" in result
        assert "Feature Ship" in result
        assert "Bug Fix" in result
        assert "Active" in result
        assert "Advisory" in result
        assert "80%" in result
        assert "60%" in result

    def test_render_lane_status_returns_no_evidence_message(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)

        result = render_lane_status(project_dir)

        assert result == "No lane evidence found."

    def test_render_lane_status_handles_empty_evidence_dir(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        evidence_dir = tmp_path / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        result = render_lane_status(project_dir)

        assert result == "No lane evidence found."

    def test_render_lane_status_handles_malformed_json(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        evidence_dir = tmp_path / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Create malformed JSON file
        (evidence_dir / "lane-bad-run-1.json").write_text("not json", encoding="utf-8")

        # Create valid file
        valid_data = {
            "schema": "LaneEvidence",
            "lane": "lane-feature-ship",
            "lane_label": "Feature Ship",
            "gate_type": "active-gated",
            "run_id": "run-1",
            "completeness": 0.5,
        }
        (evidence_dir / "lane-lane-feature-ship-run-1.json").write_text(
            json.dumps(valid_data), encoding="utf-8"
        )

        result = render_lane_status(project_dir)

        # Should still render the valid lane
        assert "Feature Ship" in result
        assert "50%" in result

    def test_render_lane_status_uses_latest_evidence_per_lane(self, tmp_path: Path) -> None:
        project_dir = str(tmp_path)
        evidence_dir = tmp_path / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Create two evidence files for same lane (different runs)
        lane_data_old = {
            "schema": "LaneEvidence",
            "lane": "lane-feature-ship",
            "lane_label": "Feature Ship",
            "gate_type": "active-gated",
            "run_id": "run-1",
            "completeness": 0.3,
        }
        lane_data_new = {
            "schema": "LaneEvidence",
            "lane": "lane-feature-ship",
            "lane_label": "Feature Ship",
            "gate_type": "active-gated",
            "run_id": "run-2",
            "completeness": 0.9,
        }

        (evidence_dir / "lane-lane-feature-ship-run-1.json").write_text(
            json.dumps(lane_data_old), encoding="utf-8"
        )
        (evidence_dir / "lane-lane-feature-ship-run-2.json").write_text(
            json.dumps(lane_data_new), encoding="utf-8"
        )

        result = render_lane_status(project_dir)

        # Should show only one lane entry (the latest)
        lines = result.split("\n")
        feature_ship_lines = [l for l in lines if "Feature Ship" in l]
        assert len(feature_ship_lines) == 1
        # Should show the latest completeness (90%)
        assert "90%" in result
