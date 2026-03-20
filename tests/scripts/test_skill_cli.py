"""Tests for skill CLI subcommands (NF6c: Human approval + promotion UX for Skill Foundry)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_cmd_skill_list_empty_registry_shows_no_skills_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test cmd_skill_list with empty registry shows 'No skills found'."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    from scripts.omg import cmd_skill_list
    import argparse

    args = argparse.Namespace()
    captured_output: list[str] = []

    def mock_print(*args_print: object) -> None:
        captured_output.append(" ".join(str(a) for a in args_print))

    monkeypatch.setattr("builtins.print", mock_print)

    exit_code = cmd_skill_list(args)

    assert exit_code == 0
    assert any("No skills found" in line for line in captured_output)


def test_cmd_skill_list_with_proposals_shows_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test cmd_skill_list with proposals shows table."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    # Create registry with active skill
    registry_dir = tmp_path / ".omg" / "state" / "skill_registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry_path = registry_dir / "compact.json"
    registry_path.write_text(
        json.dumps({"active": ["omg/control-plane"], "pruned": [], "summary_metadata": {}}),
        encoding="utf-8",
    )

    # Create a proposal
    proposals_dir = tmp_path / ".omg" / "state" / "skill-proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_path = proposals_dir / "proposal-test123.json"
    proposal_path.write_text(
        json.dumps({
            "schema": "SkillProposal",
            "proposal_id": "proposal-test123",
            "name": "omg/test-skill",
            "source": "generated",
            "status": "proposed",
            "promoted": False,
            "created_at": "2026-03-01T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    from scripts.omg import cmd_skill_list
    import argparse

    args = argparse.Namespace()
    captured_output: list[str] = []

    def mock_print(*args_print: object) -> None:
        captured_output.append(" ".join(str(a) for a in args_print))

    monkeypatch.setattr("builtins.print", mock_print)

    exit_code = cmd_skill_list(args)

    assert exit_code == 0
    output = "\n".join(captured_output)
    assert "omg/control-plane" in output
    assert "omg/test-skill" in output
    assert "active" in output
    assert "proposed" in output


def test_cmd_skill_review_with_valid_proposal_shows_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test cmd_skill_review with valid proposal shows details."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    # Create a proposal
    proposals_dir = tmp_path / ".omg" / "state" / "skill-proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_id = "proposal-review-test"
    proposal_path = proposals_dir / f"{proposal_id}.json"
    proposal_path.write_text(
        json.dumps({
            "schema": "SkillProposal",
            "proposal_id": proposal_id,
            "name": "omg/reviewed-skill",
            "source": "generated",
            "status": "proposed",
            "description": "A test skill for review",
            "promoted": False,
            "created_at": "2026-03-01T12:00:00+00:00",
        }),
        encoding="utf-8",
    )

    # Create evaluation with passing evidence
    eval_path = proposals_dir / f"{proposal_id}-eval.json"
    eval_path.write_text(
        json.dumps({
            "schema": "SkillProposalEvaluation",
            "proposal_id": proposal_id,
            "status": "evaluated",
            "promotable": True,
            "proof_gate_result": {
                "verdict": "pass",
                "blockers": [],
                "evidence_summary": {"claim_count": 2},
            },
        }),
        encoding="utf-8",
    )

    from scripts.omg import cmd_skill_review
    import argparse

    args = argparse.Namespace(proposal_id=proposal_id)
    captured_output: list[str] = []

    def mock_print(*args_print: object) -> None:
        captured_output.append(" ".join(str(a) for a in args_print))

    monkeypatch.setattr("builtins.print", mock_print)

    exit_code = cmd_skill_review(args)

    assert exit_code == 0
    output = "\n".join(captured_output)
    assert proposal_id in output
    assert "omg/reviewed-skill" in output
    assert "pass" in output.lower()
    # Should recommend more evidence since only 2 passing runs
    assert "needs more evidence" in output.lower()


def test_cmd_skill_promote_with_insufficient_evidence_exit_code_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test cmd_skill_promote with insufficient evidence returns exit code 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    # Create a proposal with only 2 passing runs
    proposals_dir = tmp_path / ".omg" / "state" / "skill-proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_id = "proposal-insufficient"
    proposal_path = proposals_dir / f"{proposal_id}.json"
    proposal_path.write_text(
        json.dumps({
            "schema": "SkillProposal",
            "proposal_id": proposal_id,
            "name": "omg/insufficient-skill",
            "source": "generated",
            "status": "proposed",
            "promoted": False,
            "created_at": "2026-03-01T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    # Create evaluation with only 2 passing runs
    eval_path = proposals_dir / f"{proposal_id}-eval.json"
    eval_path.write_text(
        json.dumps({
            "schema": "SkillProposalEvaluation",
            "proposal_id": proposal_id,
            "status": "evaluated",
            "promotable": True,
            "proof_gate_result": {
                "verdict": "pass",
                "blockers": [],
                "evidence_summary": {"claim_count": 2},
            },
        }),
        encoding="utf-8",
    )

    from scripts.omg import cmd_skill_promote
    import argparse

    args = argparse.Namespace(proposal_id=proposal_id)
    captured_output: list[str] = []

    def mock_print(*args_print: object) -> None:
        captured_output.append(" ".join(str(a) for a in args_print))

    monkeypatch.setattr("builtins.print", mock_print)

    exit_code = cmd_skill_promote(args)

    assert exit_code == 1
    output = "\n".join(captured_output)
    assert "insufficient" in output.lower() or "need" in output.lower()


def test_cmd_skill_promote_with_sufficient_evidence_exit_code_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test cmd_skill_promote with sufficient evidence returns exit code 0."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    # Create a proposal
    proposals_dir = tmp_path / ".omg" / "state" / "skill-proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_id = "proposal-sufficient"
    proposal_path = proposals_dir / f"{proposal_id}.json"
    proposal_path.write_text(
        json.dumps({
            "schema": "SkillProposal",
            "proposal_id": proposal_id,
            "name": "omg/sufficient-skill",
            "source": "generated",
            "status": "proposed",
            "promoted": False,
            "created_at": "2026-03-01T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    # Create evaluation with 3+ passing runs
    eval_path = proposals_dir / f"{proposal_id}-eval.json"
    eval_path.write_text(
        json.dumps({
            "schema": "SkillProposalEvaluation",
            "proposal_id": proposal_id,
            "status": "evaluated",
            "promotable": True,
            "proof_gate_result": {
                "verdict": "pass",
                "blockers": [],
                "evidence_summary": {"claim_count": 5},
            },
        }),
        encoding="utf-8",
    )

    from scripts.omg import cmd_skill_promote
    import argparse

    args = argparse.Namespace(proposal_id=proposal_id)
    captured_output: list[str] = []

    def mock_print(*args_print: object) -> None:
        captured_output.append(" ".join(str(a) for a in args_print))

    monkeypatch.setattr("builtins.print", mock_print)

    exit_code = cmd_skill_promote(args)

    assert exit_code == 0
    output = "\n".join(captured_output)
    assert "promoted" in output.lower()

    # Verify promotion artifact was created
    promoted_path = proposals_dir / f"{proposal_id}-promoted.json"
    assert promoted_path.exists()


def test_cmd_skill_review_not_found_returns_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test cmd_skill_review with non-existent proposal returns exit code 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    from scripts.omg import cmd_skill_review
    import argparse

    args = argparse.Namespace(proposal_id="proposal-nonexistent")
    captured_output: list[str] = []

    def mock_print(*args_print: object) -> None:
        captured_output.append(" ".join(str(a) for a in args_print))

    monkeypatch.setattr("builtins.print", mock_print)

    exit_code = cmd_skill_review(args)

    assert exit_code == 1
    output = "\n".join(captured_output)
    assert "not found" in output.lower()


def test_cmd_skill_promote_with_failing_runs_exit_code_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test cmd_skill_promote with failing runs returns exit code 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    # Create a proposal
    proposals_dir = tmp_path / ".omg" / "state" / "skill-proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_id = "proposal-failing"
    proposal_path = proposals_dir / f"{proposal_id}.json"
    proposal_path.write_text(
        json.dumps({
            "schema": "SkillProposal",
            "proposal_id": proposal_id,
            "name": "omg/failing-skill",
            "source": "generated",
            "status": "proposed",
            "promoted": False,
            "created_at": "2026-03-01T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    # Create evaluation with failing verdict
    eval_path = proposals_dir / f"{proposal_id}-eval.json"
    eval_path.write_text(
        json.dumps({
            "schema": "SkillProposalEvaluation",
            "proposal_id": proposal_id,
            "status": "failed",
            "promotable": False,
            "proof_gate_result": {
                "verdict": "fail",
                "blockers": ["test_failure"],
                "evidence_summary": {"claim_count": 1},
            },
        }),
        encoding="utf-8",
    )

    from scripts.omg import cmd_skill_promote
    import argparse

    args = argparse.Namespace(proposal_id=proposal_id)
    captured_output: list[str] = []

    def mock_print(*args_print: object) -> None:
        captured_output.append(" ".join(str(a) for a in args_print))

    monkeypatch.setattr("builtins.print", mock_print)

    exit_code = cmd_skill_promote(args)

    assert exit_code == 1
    output = "\n".join(captured_output)
    assert any(kw in output.lower() for kw in ("fail", "cannot promote", "insufficient")), \
        f"Expected rejection message, got: {output}"
