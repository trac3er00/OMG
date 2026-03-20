"""Tests for NF6a (workflow detection) and NF6b (evidence-of-success linking).

Test file for skill_evolution workflow detection and evidence linking features.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import runtime.skill_evolution as skill_evolution  # pyright: ignore[reportMissingImports]


class TestRecordWorkflowStep:
    """Tests for record_workflow_step function."""

    def test_creates_log_file(self, tmp_path: Path) -> None:
        """Test that record_workflow_step creates workflow-log.jsonl."""
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="lint",
            args={"file": "main.py"},
            success=True,
            run_id="run-001",
        )

        log_path = tmp_path / ".omg" / "state" / "skill_registry" / "workflow-log.jsonl"
        assert log_path.exists()

        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert len(entries) == 1
        assert entries[0]["tool"] == "lint"
        assert entries[0]["success"] is True
        assert entries[0]["run_id"] == "run-001"
        assert "args_hash" in entries[0]
        assert "ts" in entries[0]

    def test_appends_multiple_entries(self, tmp_path: Path) -> None:
        """Test that multiple steps are appended to the same log file."""
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="lint",
            args={},
            success=True,
            run_id="run-001",
        )
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="test",
            args={},
            success=True,
            run_id="run-001",
        )
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="build",
            args={},
            success=True,
            run_id="run-001",
        )

        log_path = tmp_path / ".omg" / "state" / "skill_registry" / "workflow-log.jsonl"
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert len(entries) == 3
        assert [e["tool"] for e in entries] == ["lint", "test", "build"]

    def test_ignores_empty_tool_name(self, tmp_path: Path) -> None:
        """Test that empty tool name is ignored."""
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="",
            args={},
            success=True,
            run_id="run-001",
        )

        log_path = tmp_path / ".omg" / "state" / "skill_registry" / "workflow-log.jsonl"
        assert not log_path.exists()

    def test_ignores_empty_run_id(self, tmp_path: Path) -> None:
        """Test that empty run_id is ignored."""
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="lint",
            args={},
            success=True,
            run_id="",
        )

        log_path = tmp_path / ".omg" / "state" / "skill_registry" / "workflow-log.jsonl"
        assert not log_path.exists()


class TestDetectReusablePatterns:
    """Tests for detect_reusable_patterns function."""

    def test_finds_repeated_sequences(self, tmp_path: Path) -> None:
        """Test that repeated successful sequences are detected."""
        # Create 3 identical successful runs
        for run_num in range(3):
            run_id = f"run-{run_num:03d}"
            for tool in ["lint", "test", "build"]:
                skill_evolution.record_workflow_step(
                    project_dir=str(tmp_path),
                    tool_name=tool,
                    args={},
                    success=True,
                    run_id=run_id,
                )

        patterns = skill_evolution.detect_reusable_patterns(str(tmp_path), min_occurrences=3)
        assert len(patterns) == 1
        assert patterns[0]["sequence"] == ["lint", "test", "build"]
        assert patterns[0]["occurrences"] == 3
        assert len(patterns[0]["run_ids"]) == 3  # type: ignore[arg-type]

    def test_ignores_sequences_below_min_occurrences(self, tmp_path: Path) -> None:
        """Test that sequences with fewer than min_occurrences are ignored."""
        # Create only 2 runs (below default min_occurrences=3)
        for run_num in range(2):
            run_id = f"run-{run_num:03d}"
            for tool in ["lint", "test"]:
                skill_evolution.record_workflow_step(
                    project_dir=str(tmp_path),
                    tool_name=tool,
                    args={},
                    success=True,
                    run_id=run_id,
                )

        patterns = skill_evolution.detect_reusable_patterns(str(tmp_path), min_occurrences=3)
        assert len(patterns) == 0

    def test_ignores_failed_runs(self, tmp_path: Path) -> None:
        """Test that runs with failed steps are not counted."""
        # Create 2 successful runs
        for run_num in range(2):
            run_id = f"run-{run_num:03d}"
            for tool in ["lint", "test"]:
                skill_evolution.record_workflow_step(
                    project_dir=str(tmp_path),
                    tool_name=tool,
                    args={},
                    success=True,
                    run_id=run_id,
                )

        # Create 1 run with a failure
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="lint",
            args={},
            success=True,
            run_id="run-002",
        )
        skill_evolution.record_workflow_step(
            project_dir=str(tmp_path),
            tool_name="test",
            args={},
            success=False,  # Failed step
            run_id="run-002",
        )

        patterns = skill_evolution.detect_reusable_patterns(str(tmp_path), min_occurrences=3)
        assert len(patterns) == 0  # Only 2 successful runs, need 3

    def test_returns_empty_for_missing_log(self, tmp_path: Path) -> None:
        """Test that missing log file returns empty list."""
        patterns = skill_evolution.detect_reusable_patterns(str(tmp_path))
        assert patterns == []

    def test_includes_confidence_score(self, tmp_path: Path) -> None:
        """Test that patterns include a confidence score."""
        for run_num in range(5):
            run_id = f"run-{run_num:03d}"
            for tool in ["lint", "test"]:
                skill_evolution.record_workflow_step(
                    project_dir=str(tmp_path),
                    tool_name=tool,
                    args={},
                    success=True,
                    run_id=run_id,
                )

        patterns = skill_evolution.detect_reusable_patterns(str(tmp_path), min_occurrences=3)
        assert len(patterns) == 1
        assert "confidence" in patterns[0]
        assert patterns[0]["confidence"] == 0.5  # 5/10


class TestAutoProposeSkill:
    """Tests for auto_propose_skill function."""

    def test_creates_proposal_for_qualifying_pattern(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that auto_propose_skill creates a proposal for qualifying patterns."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        pattern = {
            "sequence": ["lint", "test", "build"],
            "occurrences": 5,
            "run_ids": ["run-001", "run-002", "run-003", "run-004", "run-005"],
            "confidence": 0.5,
        }

        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)

        assert proposal is not None
        assert proposal["status"] == "proposed"
        assert "workflow/" in str(proposal["name"])
        assert proposal["source"] == "auto_detected"
        assert "evidence_runs" in proposal
        assert len(proposal["evidence_runs"]) == 5  # type: ignore[arg-type]

    def test_returns_none_for_insufficient_occurrences(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that patterns with < 3 occurrences return None."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        pattern = {
            "sequence": ["lint", "test"],
            "occurrences": 2,
            "run_ids": ["run-001", "run-002"],
            "confidence": 0.2,
        }

        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal is None

    def test_returns_none_for_already_proposed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that already-proposed patterns return None."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        pattern = {
            "sequence": ["lint", "test", "build"],
            "occurrences": 5,
            "run_ids": ["run-001", "run-002", "run-003", "run-004", "run-005"],
            "confidence": 0.5,
        }

        # First proposal should succeed
        proposal1 = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal1 is not None

        # Second proposal with same sequence should return None
        proposal2 = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal2 is None

    def test_returns_none_for_empty_sequence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that empty sequences return None."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        pattern = {
            "sequence": [],
            "occurrences": 5,
            "run_ids": ["run-001"],
            "confidence": 0.5,
        }

        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal is None


class TestEvaluateProposalWithEvidenceRuns:
    """Tests for evaluate_proposal checking evidence_runs (NF6b)."""

    def test_rejects_proposal_with_failed_evidence_runs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that proposals with failing evidence runs are rejected."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        # Create a proposal with evidence_runs
        pattern = {
            "sequence": ["lint", "test"],
            "occurrences": 3,
            "run_ids": ["run-001", "run-002", "run-003"],
            "confidence": 0.3,
        }
        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal is not None
        proposal_id = str(proposal["proposal_id"])

        # Record a failed verdict for one of the runs
        skill_evolution.record_run_verdict(str(tmp_path), "run-001", "fail")

        # Mock proof_gate to return pass (would pass without evidence check)
        def _fake_gate(_: dict[str, object]) -> dict[str, object]:
            return {
                "schema": "ProofGateResult",
                "verdict": "pass",
                "blockers": [],
                "evidence_summary": {"claim_count": 1},
            }

        monkeypatch.setattr(skill_evolution.proof_gate, "evaluate_proof_gate", _fake_gate)

        result = skill_evolution.evaluate_proposal(
            proposal_id,
            test_results={"claims": [{"claim_type": "tests_passed"}]},
            project_dir=str(tmp_path),
        )

        # Should be failed because evidence run failed
        assert result["status"] == "failed"
        assert result["promotable"] is False
        proof_gate_result = cast(dict[str, object], result["proof_gate_result"])
        assert "evidence_run_failed" in proof_gate_result["blockers"]  # type: ignore[operator]

    def test_increases_confidence_when_all_evidence_runs_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that confidence increases when all evidence runs pass."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        # Create a proposal with evidence_runs
        pattern = {
            "sequence": ["lint", "test"],
            "occurrences": 3,
            "run_ids": ["run-001", "run-002", "run-003"],
            "confidence": 0.3,
        }
        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal is not None
        proposal_id = str(proposal["proposal_id"])

        # Record passing verdicts for all runs
        for run_id in ["run-001", "run-002", "run-003"]:
            skill_evolution.record_run_verdict(str(tmp_path), run_id, "pass")

        # Mock proof_gate to return pass
        def _fake_gate(_: dict[str, object]) -> dict[str, object]:
            return {
                "schema": "ProofGateResult",
                "verdict": "pass",
                "blockers": [],
                "evidence_summary": {"claim_count": 1},
            }

        monkeypatch.setattr(skill_evolution.proof_gate, "evaluate_proof_gate", _fake_gate)

        result = skill_evolution.evaluate_proposal(
            proposal_id,
            test_results={"claims": [{"claim_type": "tests_passed"}]},
            project_dir=str(tmp_path),
        )

        assert result["status"] == "evaluated"
        assert result["promotable"] is True
        proof_gate_result = cast(dict[str, object], result["proof_gate_result"])
        evidence_summary = cast(dict[str, object], proof_gate_result["evidence_summary"])
        assert evidence_summary.get("evidence_runs_verified") is True
        assert evidence_summary.get("evidence_runs_count") == 3


class TestGetProposalEvidenceSummary:
    """Tests for get_proposal_evidence_summary function."""

    def test_returns_correct_counts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that evidence summary returns correct pass/fail counts."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        # Create a proposal
        pattern = {
            "sequence": ["lint", "test"],
            "occurrences": 4,
            "run_ids": ["run-001", "run-002", "run-003", "run-004"],
            "confidence": 0.4,
        }
        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal is not None
        proposal_id = str(proposal["proposal_id"])

        # Record mixed verdicts
        skill_evolution.record_run_verdict(str(tmp_path), "run-001", "pass")
        skill_evolution.record_run_verdict(str(tmp_path), "run-002", "pass")
        skill_evolution.record_run_verdict(str(tmp_path), "run-003", "fail")
        # run-004 has no verdict (unknown)

        summary = skill_evolution.get_proposal_evidence_summary(proposal_id, str(tmp_path))

        assert summary["total_runs"] == 4
        assert summary["passing_runs"] == 2
        assert summary["failing_runs"] == 1
        assert summary["verdict"] == "reject"  # Has failing runs

    def test_verdict_promote_when_all_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that verdict is 'promote' when all runs pass."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        pattern = {
            "sequence": ["lint"],
            "occurrences": 3,
            "run_ids": ["run-001", "run-002", "run-003"],
            "confidence": 0.3,
        }
        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal is not None
        proposal_id = str(proposal["proposal_id"])

        for run_id in ["run-001", "run-002", "run-003"]:
            skill_evolution.record_run_verdict(str(tmp_path), run_id, "pass")

        summary = skill_evolution.get_proposal_evidence_summary(proposal_id, str(tmp_path))

        assert summary["total_runs"] == 3
        assert summary["passing_runs"] == 3
        assert summary["failing_runs"] == 0
        assert summary["verdict"] == "promote"

    def test_verdict_review_when_unknown(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that verdict is 'review' when some verdicts are unknown."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        pattern = {
            "sequence": ["lint"],
            "occurrences": 3,
            "run_ids": ["run-001", "run-002", "run-003"],
            "confidence": 0.3,
        }
        proposal = skill_evolution.auto_propose_skill(str(tmp_path), pattern)
        assert proposal is not None
        proposal_id = str(proposal["proposal_id"])

        # Only record 2 of 3 verdicts
        skill_evolution.record_run_verdict(str(tmp_path), "run-001", "pass")
        skill_evolution.record_run_verdict(str(tmp_path), "run-002", "pass")
        # run-003 has no verdict

        summary = skill_evolution.get_proposal_evidence_summary(proposal_id, str(tmp_path))

        assert summary["total_runs"] == 3
        assert summary["passing_runs"] == 2
        assert summary["failing_runs"] == 0
        assert summary["verdict"] == "review"  # Not all runs have verdicts

    def test_returns_review_for_missing_proposal(self, tmp_path: Path) -> None:
        """Test that missing proposal returns review verdict with zero counts."""
        summary = skill_evolution.get_proposal_evidence_summary(
            "nonexistent-proposal", str(tmp_path)
        )

        assert summary["total_runs"] == 0
        assert summary["passing_runs"] == 0
        assert summary["failing_runs"] == 0
        assert summary["verdict"] == "review"
