from __future__ import annotations

from pathlib import Path

import yaml

import pytest

from hooks import setup_wizard

from runtime.runtime_profile import (
    load_canonical_mode_profile,
    load_runtime_profile,
    resolve_parallel_workers,
)


def test_load_runtime_profile_defaults_to_balanced(tmp_path: Path):
    result = load_runtime_profile(str(tmp_path))
    assert result["profile"] == "balanced"
    assert result["max_workers"] == 3


def test_resolve_parallel_workers_respects_profile_and_cli_caps(tmp_path: Path):
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omg" / "runtime.yaml").write_text("profile: eco\n", encoding="utf-8")
    dumped = yaml.safe_dump(
        {
            "cli_configs": {
                "codex": {"max_parallel_agents": 4},
                "gemini": {"max_parallel_agents": 1},
            }
        }
    )
    (omg_state / "cli-config.yaml").write_text(dumped or "", encoding="utf-8")

    assert resolve_parallel_workers(str(tmp_path), requested_workers=5) == 1


def test_canonical_mode_profile_chill_has_lower_concurrency_than_focused() -> None:
    chill = load_canonical_mode_profile("chill")
    focused = load_canonical_mode_profile("focused")

    assert isinstance(chill["concurrency"], int)
    assert isinstance(focused["concurrency"], int)
    assert chill["concurrency"] < focused["concurrency"]
    assert chill["noise_level"] == "quiet"


def test_canonical_mode_profile_exploratory_enables_background_verification() -> None:
    exploratory = load_canonical_mode_profile("exploratory")
    assert exploratory["background_verification"] is True


def test_canonical_mode_profile_unknown_mode_raises() -> None:
    with pytest.raises(ValueError, match="Unknown canonical mode"):
        _ = load_canonical_mode_profile("turbo")


def test_profile_learning_sections_present_with_defaults(tmp_path: Path) -> None:
    setup_wizard.set_preferences(str(tmp_path), {})
    profile_path = tmp_path / ".omg" / "state" / "profile.yaml"
    profile_payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    assert profile_payload["preferences"]["architecture_requests"] == []
    assert profile_payload["preferences"]["constraints"] == {}
    assert profile_payload["preferences"]["routing"]["prefer_clarification"] is False
    assert profile_payload["user_vector"]["tags"] == []
    assert profile_payload["user_vector"]["summary"] == ""
    assert profile_payload["user_vector"]["confidence"] == 0.0
    assert profile_payload["profile_provenance"]["recent_updates"] == []


def test_profile_learning_sections_normalize_and_enforce_bounds(tmp_path: Path) -> None:
    setup_wizard.set_preferences(
        str(tmp_path),
        {
            "preferences": {
                "architecture_requests": [f" Request {idx} " for idx in range(1, 12)],
                "constraints": {
                    " API Cost ": " Minimize ",
                    "parallel pipelines": " 2 ",
                },
                "routing": {"prefer_clarification": 1},
            },
            "user_vector": {
                "tags": [f" Tag {idx} " for idx in range(1, 20)],
                "summary": " ".join(["alpha"] * 300),
                "confidence": "1.5",
            },
            "profile_provenance": {
                "recent_updates": [
                    {
                        "run_id": f"run-{idx}",
                        "source": "setup_wizard",
                        "field": "preferences.constraints.api_cost",
                        "updated_at": "2026-03-09T00:00:00Z",
                    }
                    for idx in range(1, 10)
                ]
            },
        },
    )

    profile_path = tmp_path / ".omg" / "state" / "profile.yaml"
    profile_payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    assert len(profile_payload["preferences"]["architecture_requests"]) == 8
    assert profile_payload["preferences"]["constraints"]["api_cost"] == "minimize"
    assert profile_payload["preferences"]["constraints"]["parallel_pipelines"] == "2"
    assert profile_payload["preferences"]["routing"]["prefer_clarification"] is True

    assert len(profile_payload["user_vector"]["tags"]) == 12
    assert all(tag == tag.lower() for tag in profile_payload["user_vector"]["tags"])
    assert len(profile_payload["user_vector"]["summary"]) == 240
    assert profile_payload["user_vector"]["confidence"] == 1.0

    assert len(profile_payload["profile_provenance"]["recent_updates"]) == 5
    assert profile_payload["profile_provenance"]["recent_updates"][0]["run_id"] == "run-1"


def test_profile_learning_sections_handle_absent_or_invalid_blocks(tmp_path: Path) -> None:
    setup_wizard.set_preferences(
        str(tmp_path),
        {
            "preferences": "invalid",
            "user_vector": None,
            "profile_provenance": {"recent_updates": ["invalid-entry"]},
        },
    )

    profile_path = tmp_path / ".omg" / "state" / "profile.yaml"
    profile_payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    assert profile_payload["preferences"] == {
        "architecture_requests": [],
        "constraints": {},
        "routing": {"prefer_clarification": False},
    }
    assert profile_payload["user_vector"] == {
        "tags": [],
        "summary": "",
        "confidence": 0.0,
    }
    assert profile_payload["profile_provenance"] == {"recent_updates": []}
