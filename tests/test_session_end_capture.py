#!/usr/bin/env python3
"""Unit tests for hooks/session-end-capture.py."""
import json
import os
import sys
import subprocess
from pathlib import Path

import yaml

# Add hooks to path
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)


def test_exits_zero_with_valid_input():
    """Test that session-end-capture exits 0 with valid session_id."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")

    # Valid input with session_id
    input_data = json.dumps({"session_id": "test-session-123", "cwd": "/tmp"})

    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"


def test_exits_zero_with_invalid_json():
    """Test that session-end-capture exits 0 with invalid JSON (crash isolation)."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")

    # Invalid JSON input
    input_data = "{ invalid json }"

    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Expected exit 0 on invalid JSON, got {result.returncode}. stderr: {result.stderr}"


def test_exits_zero_with_missing_session_id():
    """Test that session-end-capture exits 0 even with missing session_id."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")

    # Valid JSON but no session_id
    input_data = json.dumps({"cwd": "/tmp"})

    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Expected exit 0 with missing session_id, got {result.returncode}"


def test_exits_zero_with_empty_input():
    """Test that session-end-capture exits 0 with empty input."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")

    # Empty input
    input_data = ""

    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Expected exit 0 with empty input, got {result.returncode}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_hook(project_dir: Path, run_id: str, home_dir: Path) -> subprocess.CompletedProcess[str]:
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")
    input_data = json.dumps({"session_id": run_id, "cwd": str(project_dir)})
    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    return subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True,
        env=env,
    )


def _seed_profile(project_dir: Path) -> Path:
    profile_path = project_dir / ".omg" / "state" / "profile.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        "name: omg-project\n"
        "description: initialized\n"
        "language: unknown\n"
        "framework: unknown\n"
        "stack: []\n"
        "conventions: {}\n"
        "ai_behavior: {}\n"
        "preferences:\n"
        "  architecture_requests: []\n"
        "  constraints: {}\n"
        "user_vector:\n"
        "  tags: []\n"
        "profile_provenance:\n"
        "  recent_updates: []\n",
        encoding="utf-8",
    )
    return profile_path


def _add_signal(
    home_dir: Path,
    *,
    project_dir: Path,
    field: str,
    value: str,
    source: str,
    confidence: float,
    run_id: str,
    contradicted: bool = False,
) -> None:
    store_path = home_dir / ".omg" / "shared-memory" / "store.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": f"{source}-{field}-{value}-{run_id}".replace(" ", "-").replace("/", "-"),
        "key": "pref-signal",
        "content": json.dumps(
            {
                "field": field,
                "value": value,
                "source": source,
                "confidence": confidence,
                "project_scope": str(project_dir),
                "run_id": run_id,
                "contradicted": contradicted,
            }
        ),
        "source_cli": "claude",
        "tags": [f"project_scope:{project_dir}"],
        "created_at": "2026-03-09T00:00:00+00:00",
        "updated_at": "2026-03-09T00:00:00+00:00",
    }
    existing = []
    if store_path.exists():
        existing = json.loads(store_path.read_text(encoding="utf-8"))
    existing.append(payload)
    store_path.write_text(json.dumps(existing), encoding="utf-8")


def test_promotes_explicit_preference_once_with_provenance(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    run_id = "run-explicit"
    profile_path = _seed_profile(project_dir)

    _write_json(
        project_dir / ".omg" / "state" / "intent_gate" / f"{run_id}.json",
        {"run_id": run_id, "requires_clarification": False, "intent_class": "preference_memory", "confidence": 0.95},
    )
    _write_json(project_dir / ".omg" / "state" / "council_verdicts" / f"{run_id}.json", {"status": "ok", "verdicts": {}})
    _write_json(
        project_dir / ".omg" / "state" / "session_health" / f"{run_id}.json",
        {"status": "ok", "recommended_action": "continue"},
    )

    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.architecture_requests",
        value="layered monolith",
        source="explicit_user",
        confidence=0.99,
        run_id=run_id,
    )

    first = _run_hook(project_dir, run_id, home_dir)
    second = _run_hook(project_dir, run_id, home_dir)

    assert first.returncode == 0
    assert second.returncode == 0
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert profile["preferences"]["architecture_requests"] == ["layered monolith"]
    updates = profile["profile_provenance"]["recent_updates"]
    assert len(updates) == 1
    assert updates[0]["run_id"] == run_id
    assert updates[0]["source"] == "explicit_user"
    assert updates[0]["field"] == "preferences.architecture_requests"

    governed = profile["governed_preferences"]["style"]
    assert len(governed) == 1
    assert governed[0]["source"] == "explicit_user"
    assert governed[0]["section"] == "style"
    assert governed[0]["confirmation_state"] == "confirmed"
    assert governed[0]["learned_at"].endswith("Z")
    assert governed[0]["updated_at"].endswith("Z")


def test_inferred_preference_requires_two_project_local_observations(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    profile_path = _seed_profile(project_dir)
    run_first = "run-inf-1"
    run_second = "run-inf-2"

    for run_id in (run_first, run_second):
        _write_json(
            project_dir / ".omg" / "state" / "intent_gate" / f"{run_id}.json",
            {"run_id": run_id, "requires_clarification": False, "intent_class": "preference_memory", "confidence": 0.9},
        )
        _write_json(project_dir / ".omg" / "state" / "council_verdicts" / f"{run_id}.json", {"status": "ok", "verdicts": {}})
        _write_json(
            project_dir / ".omg" / "state" / "session_health" / f"{run_id}.json",
            {"status": "ok", "recommended_action": "continue"},
        )

    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.constraints.api_cost",
        value="minimize",
        source="inferred_observation",
        confidence=0.9,
        run_id=run_first,
    )

    first = _run_hook(project_dir, run_first, home_dir)
    profile_after_first = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert first.returncode == 0
    assert profile_after_first["preferences"]["constraints"] == {}

    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.constraints.api_cost",
        value="minimize",
        source="inferred_observation",
        confidence=0.95,
        run_id=run_second,
    )
    second = _run_hook(project_dir, run_second, home_dir)

    assert second.returncode == 0
    profile_after_second = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert profile_after_second["preferences"]["constraints"]["api_cost"] == "minimize"

    governed = profile_after_second["governed_preferences"]["style"]
    assert len(governed) == 1
    assert governed[0]["field"] == "preferences.constraints.api_cost"
    assert governed[0]["confirmation_state"] == "inferred"
    assert governed[0]["decay_metadata"]["decay_reason"] == "inferred_signal"


def test_ignores_low_confidence_or_contradicted_signals(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    run_id = "run-ignore"
    profile_path = _seed_profile(project_dir)

    _write_json(
        project_dir / ".omg" / "state" / "intent_gate" / f"{run_id}.json",
        {"run_id": run_id, "requires_clarification": False, "intent_class": "preference_memory", "confidence": 0.92},
    )
    _write_json(
        project_dir / ".omg" / "state" / "council_verdicts" / f"{run_id}.json",
        {
            "status": "running",
            "verdicts": {
                "policy": {
                    "verdict": "warn",
                    "reason": "contradiction on preferences.architecture_requests",
                }
            },
        },
    )
    _write_json(
        project_dir / ".omg" / "state" / "session_health" / f"{run_id}.json",
        {"status": "ok", "recommended_action": "continue"},
    )

    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.architecture_requests",
        value="event sourced",
        source="explicit_user",
        confidence=0.2,
        run_id=run_id,
    )
    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.architecture_requests",
        value="clean architecture",
        source="explicit_user",
        confidence=0.95,
        run_id=run_id,
        contradicted=True,
    )

    result = _run_hook(project_dir, run_id, home_dir)

    assert result.returncode == 0
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert profile["preferences"]["architecture_requests"] == []
    assert profile["profile_provenance"]["recent_updates"] == []
    assert profile["governed_preferences"] == {"style": [], "safety": []}


def test_destructive_preference_marked_pending_confirmation(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    run_id = "run-destructive"
    profile_path = _seed_profile(project_dir)

    _write_json(project_dir / ".omg" / "state" / "intent_gate" / f"{run_id}.json", {"run_id": run_id, "requires_clarification": False})
    _write_json(project_dir / ".omg" / "state" / "council_verdicts" / f"{run_id}.json", {"status": "ok", "verdicts": {}})
    _write_json(project_dir / ".omg" / "state" / "session_health" / f"{run_id}.json", {"status": "ok", "recommended_action": "continue"})

    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.constraints.safety_guardrails",
        value="disable",
        source="explicit_user",
        confidence=0.98,
        run_id=run_id,
    )

    result = _run_hook(project_dir, run_id, home_dir)
    assert result.returncode == 0

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert profile["preferences"]["constraints"] == {}
    safety = profile["governed_preferences"]["safety"]
    assert len(safety) == 1
    assert safety[0]["confirmation_state"] == "pending_confirmation"
    assert safety[0]["section"] == "safety"


def test_decay_metadata_recorded_but_safety_is_immune(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    profile_path = _seed_profile(project_dir)
    run_a = "run-decay-a"
    run_b = "run-decay-b"

    for run_id in (run_a, run_b):
        _write_json(project_dir / ".omg" / "state" / "intent_gate" / f"{run_id}.json", {"run_id": run_id, "requires_clarification": False})
        _write_json(project_dir / ".omg" / "state" / "council_verdicts" / f"{run_id}.json", {"status": "ok", "verdicts": {}})
        _write_json(project_dir / ".omg" / "state" / "session_health" / f"{run_id}.json", {"status": "ok", "recommended_action": "continue"})

    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.constraints.api_cost",
        value="minimize",
        source="inferred_observation",
        confidence=0.9,
        run_id=run_a,
    )
    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.constraints.api_cost",
        value="minimize",
        source="inferred_observation",
        confidence=0.95,
        run_id=run_b,
    )

    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.constraints.safety_mode",
        value="strict",
        source="inferred_observation",
        confidence=0.95,
        run_id=run_a,
    )
    _add_signal(
        home_dir,
        project_dir=project_dir,
        field="preferences.constraints.safety_mode",
        value="strict",
        source="inferred_observation",
        confidence=0.96,
        run_id=run_b,
    )

    first = _run_hook(project_dir, run_a, home_dir)
    second = _run_hook(project_dir, run_b, home_dir)
    assert first.returncode == 0
    assert second.returncode == 0

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    style = profile["governed_preferences"]["style"]
    safety = profile["governed_preferences"]["safety"]

    style_entry = [e for e in style if e["field"] == "preferences.constraints.api_cost"][0]
    assert style_entry["decay_metadata"]["decay_score"] == 0.0

    safety_entry = [e for e in safety if e["field"] == "preferences.constraints.safety_mode"][0]
    assert "decay_metadata" not in safety_entry
