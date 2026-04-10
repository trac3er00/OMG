"""Tests for TrajectoryTracker JSONL export and CI artifact metadata."""
from __future__ import annotations

import json
import os

import pytest

from runtime.eval_gate import TrajectoryTracker


@pytest.fixture
def tmp_output(tmp_path):
    return str(tmp_path / "eval-history")


def test_trajectory_export(tmp_output):
    tracker = TrajectoryTracker(session_id="sess-001", output_dir=tmp_output)
    tracker.record(tool="Bash", decision="allow", outcome="success")
    path = tracker.export_jsonl()

    assert os.path.exists(path)
    with open(path) as f:
        lines = f.read().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    for key in ("tool", "decision", "outcome", "timestamp", "session_id"):
        assert key in entry
    assert entry["tool"] == "Bash"
    assert entry["decision"] == "allow"
    assert entry["outcome"] == "success"
    assert entry["session_id"] == "sess-001"


def test_jsonl_format(tmp_output):
    tracker = TrajectoryTracker(session_id="sess-fmt", output_dir=tmp_output)
    tracker.record(tool="Read", decision="allow", outcome="ok")
    tracker.record(tool="Write", decision="deny", outcome="blocked")
    path = tracker.export_jsonl()

    with open(path) as f:
        for line in f:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)


def test_ci_artifact(tmp_output):
    tracker = TrajectoryTracker(session_id="sess-ci", output_dir=tmp_output)
    tracker.record(tool="Bash", decision="allow", outcome="success")
    tracker.record(tool="Edit", decision="allow", outcome="success")
    artifact = tracker.to_ci_artifact()

    assert artifact["session_id"] == "sess-ci"
    assert artifact["entry_count"] == 2
    assert "trajectory-sess-ci.jsonl" in artifact["filepath"]
    assert sorted(artifact["tools_used"]) == ["Bash", "Edit"]


def test_empty_trajectory(tmp_output):
    tracker = TrajectoryTracker(session_id="sess-empty", output_dir=tmp_output)
    path = tracker.export_jsonl()

    assert os.path.exists(path)
    with open(path) as f:
        content = f.read()
    assert content == ""


def test_multiple_entries(tmp_output):
    tracker = TrajectoryTracker(session_id="sess-multi", output_dir=tmp_output)
    tools = ["Bash", "Read", "Edit", "Write", "Grep"]
    for t in tools:
        tracker.record(tool=t, decision="allow", outcome="success")

    path = tracker.export_jsonl()
    with open(path) as f:
        lines = f.read().strip().splitlines()
    assert len(lines) == 5

    parsed_tools = [json.loads(line)["tool"] for line in lines]
    assert parsed_tools == tools
