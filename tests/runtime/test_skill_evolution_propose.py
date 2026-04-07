from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import runtime.skill_evolution as skill_evolution  # pyright: ignore[reportMissingImports]


FOUR_TOOL_SEQ = ["grep", "read", "edit", "bash"]


def _make_sessions(sequence: list[str], count: int) -> list[list[str]]:
    return [list(sequence) for _ in range(count)]


def test_auto_propose_generates_proposal_from_repeated_sequence(tmp_path: Path) -> None:
    sessions = _make_sessions(FOUR_TOOL_SEQ, 3)
    proposals_dir = str(tmp_path / "proposals")

    proposals = skill_evolution.run_auto_propose(
        sessions,
        proposals_dir=proposals_dir,
        min_sequence_length=3,
        min_occurrences=3,
    )

    assert len(proposals) > 0
    names = [p.name for p in proposals]
    assert any("grep" in n for n in names)


def test_proposal_file_exists_on_disk(tmp_path: Path) -> None:
    sessions = _make_sessions(FOUR_TOOL_SEQ, 3)
    proposals_dir = str(tmp_path / "proposals")

    proposals = skill_evolution.run_auto_propose(
        sessions,
        proposals_dir=proposals_dir,
        min_sequence_length=3,
        min_occurrences=3,
    )

    for proposal in proposals:
        filepath = os.path.join(proposals_dir, f"{proposal.name}.json")
        assert os.path.exists(filepath), f"Missing proposal file: {filepath}"
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        assert data["status"] == "proposed"


def test_proposal_fields_complete(tmp_path: Path) -> None:
    sessions = _make_sessions(FOUR_TOOL_SEQ, 4)
    proposals_dir = str(tmp_path / "proposals")

    proposals = skill_evolution.run_auto_propose(
        sessions,
        proposals_dir=proposals_dir,
        min_sequence_length=3,
        min_occurrences=3,
    )

    for proposal in proposals:
        d = proposal.to_dict()
        assert "name" in d and d["name"]
        assert "trigger" in d and d["trigger"]
        tool_seq = d["tool_sequence"]
        assert isinstance(tool_seq, list) and len(tool_seq) >= 3
        assert "expected_outcome" in d and d["expected_outcome"]
        occ = d["occurrence_count"]
        assert isinstance(occ, int) and occ >= 3
        assert d["status"] == "proposed"


def test_min_occurrences_filters_below_threshold() -> None:
    sessions = _make_sessions(FOUR_TOOL_SEQ, 2)

    patterns = skill_evolution.detect_repeated_patterns(
        sessions,
        min_sequence_length=3,
        min_occurrences=3,
    )

    assert patterns == []


def test_min_length_filters_short_sequences() -> None:
    short_seq = ["grep", "read"]
    sessions = _make_sessions(short_seq, 5)

    patterns = skill_evolution.detect_repeated_patterns(
        sessions,
        min_sequence_length=3,
        min_occurrences=3,
    )

    assert patterns == []


def test_tool_sequence_len() -> None:
    seq = skill_evolution.ToolSequence(("a", "b", "c"))
    assert len(seq) == 3


def test_skill_proposal_to_dict_roundtrip() -> None:
    seq = skill_evolution.ToolSequence(("grep", "read", "edit"))
    proposal = skill_evolution.auto_propose_skill(seq, occurrence_count=5)

    d = proposal.to_dict()
    assert d["tool_sequence"] == ["grep", "read", "edit"]
    assert d["occurrence_count"] == 5
    assert d["status"] == "proposed"


def test_detect_patterns_sorted_by_count_descending() -> None:
    sessions: list[list[str]] = [
        ["a", "b", "c", "d"],
        ["a", "b", "c", "d"],
        ["a", "b", "c", "d"],
        ["x", "y", "z"],
        ["x", "y", "z"],
        ["x", "y", "z"],
    ]

    patterns = skill_evolution.detect_repeated_patterns(
        sessions,
        min_sequence_length=3,
        min_occurrences=3,
    )

    counts = [count for _, count in patterns]
    assert counts == sorted(counts, reverse=True)


def test_save_skill_proposal_writes_valid_json(tmp_path: Path) -> None:
    seq = skill_evolution.ToolSequence(("grep", "read", "edit"))
    proposal = skill_evolution.auto_propose_skill(seq, occurrence_count=3)
    proposals_dir = str(tmp_path / "proposals")

    filepath = skill_evolution.save_skill_proposal(proposal, proposals_dir)

    data = json.loads(Path(filepath).read_text(encoding="utf-8"))
    assert data["name"] == proposal.name
    assert data["tool_sequence"] == ["grep", "read", "edit"]
