"""Tests for NF3a (one-task-per-session) and NF3b (protected handoff snapshot)."""

import json
from pathlib import Path

from runtime.context_engine import (
    create_handoff_snapshot,
    detect_task_drift,
    get_active_task,
    list_handoff_snapshots,
    set_task_focus,
)


def _write_json(path: Path, data: dict) -> None:
    """Helper to write JSON files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# NF3a: get_active_task tests
# ---------------------------------------------------------------------------


def test_get_active_task_no_session_returns_none(tmp_path):
    """When session.json does not exist, get_active_task returns None."""
    result = get_active_task(str(tmp_path))
    assert result is None


def test_get_active_task_with_session_returns_task_dict(tmp_path):
    """When session.json has task_focus, get_active_task returns the task dict."""
    session_path = tmp_path / ".omg" / "state" / "session.json"
    _write_json(
        session_path,
        {
            "task_focus": {
                "task": "Implement pagination for user list",
                "started_at": "2026-03-19T10:00:00+00:00",
                "files_touched": ["src/api/users.py", "tests/test_users.py"],
            }
        },
    )

    result = get_active_task(str(tmp_path))

    assert result is not None
    assert result["task"] == "Implement pagination for user list"
    assert result["started_at"] == "2026-03-19T10:00:00+00:00"
    assert result["files_touched"] == ["src/api/users.py", "tests/test_users.py"]


def test_get_active_task_missing_task_focus_returns_none(tmp_path):
    """When session.json exists but has no task_focus, returns None."""
    session_path = tmp_path / ".omg" / "state" / "session.json"
    _write_json(session_path, {"other_field": "value"})

    result = get_active_task(str(tmp_path))
    assert result is None


def test_get_active_task_empty_task_returns_none(tmp_path):
    """When task_focus.task is empty, returns None."""
    session_path = tmp_path / ".omg" / "state" / "session.json"
    _write_json(
        session_path,
        {"task_focus": {"task": "", "started_at": "2026-03-19T10:00:00+00:00"}},
    )

    result = get_active_task(str(tmp_path))
    assert result is None


# ---------------------------------------------------------------------------
# NF3a: detect_task_drift tests
# ---------------------------------------------------------------------------


def test_detect_task_drift_no_active_task_returns_no_drift(tmp_path):
    """When no active task, detect_task_drift returns drift=False, action=none."""
    result = detect_task_drift("Add pagination to users", None)

    assert result["drift"] is False
    assert result["action"] == "none"


def test_detect_task_drift_matching_prompt_returns_no_drift(tmp_path):
    """When prompt contains task keywords, returns drift=False."""
    active_task = {
        "task": "Implement pagination for user list endpoint",
        "started_at": "2026-03-19T10:00:00+00:00",
        "files_touched": [],
    }

    result = detect_task_drift("Add pagination to the users list", active_task)

    assert result["drift"] is False
    assert result["suggested_action"] == "continue"
    assert result["active_task"] == "implement pagination for user list endpoint"


def test_detect_task_drift_unrelated_prompt_returns_drift(tmp_path):
    """When prompt has no task keywords, returns drift=True."""
    active_task = {
        "task": "Implement pagination for user list endpoint",
        "started_at": "2026-03-19T10:00:00+00:00",
        "files_touched": [],
    }

    result = detect_task_drift("Fix the authentication bug in login flow", active_task)

    assert result["drift"] is True
    assert result["suggested_action"] == "snapshot"
    assert result["confidence"] > 0.5


def test_detect_task_drift_partial_match_continues(tmp_path):
    """When some task keywords match, continues (no drift)."""
    active_task = {
        "task": "Add error handling and validation to API",
        "started_at": "2026-03-19T10:00:00+00:00",
        "files_touched": [],
    }

    # Contains "error" and "api" - should match enough
    result = detect_task_drift("The API returns a 500 error", active_task)

    assert result["drift"] is False
    assert result["suggested_action"] == "continue"


# ---------------------------------------------------------------------------
# NF3a: set_task_focus tests
# ---------------------------------------------------------------------------


def test_set_task_focus_writes_correctly(tmp_path):
    """set_task_focus writes task_focus to session.json."""
    set_task_focus(
        str(tmp_path),
        task="Implement feature X",
        files=["src/feature_x.py"],
    )

    session_path = tmp_path / ".omg" / "state" / "session.json"
    assert session_path.exists()

    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert "task_focus" in data
    assert data["task_focus"]["task"] == "Implement feature X"
    assert data["task_focus"]["files_touched"] == ["src/feature_x.py"]
    assert "started_at" in data["task_focus"]


def test_set_task_focus_preserves_existing_data(tmp_path):
    """set_task_focus preserves other fields in session.json."""
    session_path = tmp_path / ".omg" / "state" / "session.json"
    _write_json(session_path, {"existing_field": "preserved_value"})

    set_task_focus(str(tmp_path), task="New task")

    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["existing_field"] == "preserved_value"
    assert data["task_focus"]["task"] == "New task"


def test_set_task_focus_no_files_defaults_to_empty_list(tmp_path):
    """When files is None, set_task_focus uses empty list."""
    set_task_focus(str(tmp_path), task="Task without files")

    session_path = tmp_path / ".omg" / "state" / "session.json"
    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["task_focus"]["files_touched"] == []


# ---------------------------------------------------------------------------
# NF3b: create_handoff_snapshot tests
# ---------------------------------------------------------------------------


def test_create_handoff_snapshot_creates_file(tmp_path):
    """create_handoff_snapshot creates a snapshot file and returns its path."""
    # Set up some state
    set_task_focus(str(tmp_path), task="Test task", files=["file1.py"])
    plan_path = tmp_path / ".omg" / "state" / "_plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("# Plan\n\n- Step 1\n- Step 2", encoding="utf-8")

    snapshot_path = create_handoff_snapshot(str(tmp_path))

    assert Path(snapshot_path).exists()
    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    assert data["schema"] == "HandoffSnapshot"
    assert data["schema_version"] == "1.0.0"
    assert data["active_task"]["task"] == "Test task"
    assert "# Plan" in data["plan_state"]


def test_create_handoff_snapshot_includes_checklist(tmp_path):
    """create_handoff_snapshot includes checklist state."""
    checklist_path = tmp_path / ".omg" / "state" / "_checklist.md"
    checklist_path.parent.mkdir(parents=True, exist_ok=True)
    checklist_path.write_text("- [x] Done\n- [ ] Pending", encoding="utf-8")

    snapshot_path = create_handoff_snapshot(str(tmp_path))

    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    assert "- [x] Done" in data["checklist_state"]


def test_create_handoff_snapshot_no_state_works(tmp_path):
    """create_handoff_snapshot works even with no existing state."""
    snapshot_path = create_handoff_snapshot(str(tmp_path))

    assert Path(snapshot_path).exists()
    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    assert data["active_task"] is None
    assert data["plan_state"] is None
    assert data["checklist_state"] is None


# ---------------------------------------------------------------------------
# NF3b: list_handoff_snapshots tests
# ---------------------------------------------------------------------------


def test_list_handoff_snapshots_returns_sorted_list(tmp_path):
    """list_handoff_snapshots returns snapshots sorted by timestamp (newest first)."""
    snapshots_dir = tmp_path / ".omg" / "state" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Create snapshots with different timestamps
    _write_json(
        snapshots_dir / "20260319T100000Z.json",
        {
            "timestamp": "20260319T100000Z",
            "active_task": {"task": "First task"},
            "files_touched": ["a.py"],
        },
    )
    _write_json(
        snapshots_dir / "20260319T110000Z.json",
        {
            "timestamp": "20260319T110000Z",
            "active_task": {"task": "Second task"},
            "files_touched": ["b.py", "c.py"],
        },
    )
    _write_json(
        snapshots_dir / "20260319T090000Z.json",
        {
            "timestamp": "20260319T090000Z",
            "active_task": {"task": "Oldest task"},
            "files_touched": [],
        },
    )

    result = list_handoff_snapshots(str(tmp_path))

    assert len(result) == 3
    # Newest first
    assert result[0]["timestamp"] == "20260319T110000Z"
    assert result[0]["task"] == "Second task"
    assert result[0]["file_count"] == 2
    # Then middle
    assert result[1]["timestamp"] == "20260319T100000Z"
    assert result[1]["task"] == "First task"
    assert result[1]["file_count"] == 1
    # Then oldest
    assert result[2]["timestamp"] == "20260319T090000Z"
    assert result[2]["task"] == "Oldest task"
    assert result[2]["file_count"] == 0


def test_list_handoff_snapshots_empty_dir_returns_empty_list(tmp_path):
    """When no snapshots exist, returns empty list."""
    result = list_handoff_snapshots(str(tmp_path))
    assert result == []


def test_list_handoff_snapshots_ignores_non_json_files(tmp_path):
    """list_handoff_snapshots ignores non-JSON files."""
    snapshots_dir = tmp_path / ".omg" / "state" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Create a non-JSON file and a subdirectory
    (snapshots_dir / "readme.txt").write_text("Not a snapshot", encoding="utf-8")
    (snapshots_dir / "subdir").mkdir()

    _write_json(
        snapshots_dir / "20260319T100000Z.json",
        {"timestamp": "20260319T100000Z", "active_task": {"task": "Valid"}},
    )

    result = list_handoff_snapshots(str(tmp_path))

    assert len(result) == 1
    assert result[0]["task"] == "Valid"
