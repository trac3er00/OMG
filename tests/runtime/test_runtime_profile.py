from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

import pytest

from hooks import setup_wizard

from runtime.profile_io import (
    load_profile,
    save_profile,
    profile_version_from_map,
)
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
    assert profile_payload["governed_preferences"] == {"style": [], "safety": []}


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
            "governed_preferences": {
                "style": [
                    {
                        "field": "preferences.architecture_requests",
                        "value": "layered monolith",
                        "source": "explicit_user",
                        "learned_at": "2026-03-09T00:00:00Z",
                        "updated_at": "2026-03-09T00:00:00Z",
                        "section": "style",
                        "confirmation_state": "confirmed",
                    }
                ],
                "safety": [
                    {
                        "field": "preferences.constraints.safety_mode",
                        "value": "strict",
                        "source": "explicit_user",
                        "learned_at": "2026-03-09T00:00:00Z",
                        "updated_at": "2026-03-09T00:00:00Z",
                        "section": "safety",
                        "confirmation_state": "confirmed",
                    }
                ],
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

    assert profile_payload["governed_preferences"]["style"][0]["section"] == "style"
    assert profile_payload["governed_preferences"]["safety"][0]["section"] == "safety"
    assert profile_payload["governed_preferences"]["style"][0]["confirmation_state"] == "confirmed"


def test_profile_learning_sections_handle_absent_or_invalid_blocks(tmp_path: Path) -> None:
    setup_wizard.set_preferences(
        str(tmp_path),
        {
            "preferences": "invalid",
            "user_vector": None,
            "profile_provenance": {"recent_updates": ["invalid-entry"]},
            "governed_preferences": {"style": [{"field": "x"}], "safety": "bad"},
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
    assert profile_payload["governed_preferences"] == {"style": [], "safety": []}


# -- profile_io tests ---------------------------------------------------


def test_profile_io_load_returns_dict_from_yaml(tmp_path: Path) -> None:
    """load_profile reads YAML and returns a dict."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "name: test-project\nlanguage: python\n",
        encoding="utf-8",
    )
    result = load_profile(str(profile_path))
    assert isinstance(result, dict)
    assert result["name"] == "test-project"
    assert result["language"] == "python"


def test_profile_io_load_handles_json_shaped_yaml(tmp_path: Path) -> None:
    """load_profile transparently reads JSON-shaped content in a .yaml file."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        json.dumps({"name": "legacy", "language": "go"}, indent=2) + "\n",
        encoding="utf-8",
    )
    result = load_profile(str(profile_path))
    assert isinstance(result, dict)
    assert result["name"] == "legacy"


def test_profile_io_load_missing_file_returns_empty(tmp_path: Path) -> None:
    """load_profile returns {} when file doesn't exist."""
    result = load_profile(str(tmp_path / "no-such-file.yaml"))
    assert result == {}


def test_profile_io_save_writes_yaml_not_json(tmp_path: Path) -> None:
    """save_profile always writes YAML-formatted output."""
    profile_path = tmp_path / "profile.yaml"
    data = {"name": "test", "preferences": {"constraints": {"api_cost": "minimize"}}}
    save_profile(str(profile_path), data)
    raw = profile_path.read_text(encoding="utf-8")
    # Must be YAML, not JSON (no opening brace)
    assert not raw.lstrip().startswith("{")
    # Must round-trip correctly
    loaded = yaml.safe_load(raw)
    assert loaded == data


def test_profile_io_save_creates_parent_dirs(tmp_path: Path) -> None:
    """save_profile creates parent directories if they don't exist."""
    profile_path = tmp_path / "deep" / "nested" / "profile.yaml"
    save_profile(str(profile_path), {"name": "nested"})
    assert profile_path.exists()
    assert yaml.safe_load(profile_path.read_text(encoding="utf-8"))["name"] == "nested"


def test_profile_version_from_map_is_deterministic() -> None:
    """Same data -> same version, regardless of insertion order."""
    data_a = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
    data_b = {"a": 2, "m": {"a": 4, "b": 3}, "z": 1}
    assert profile_version_from_map(data_a) == profile_version_from_map(data_b)


def test_profile_version_from_map_differs_for_different_data() -> None:
    """Different data -> different version."""
    v1 = profile_version_from_map({"name": "a"})
    v2 = profile_version_from_map({"name": "b"})
    assert v1 != v2


def test_profile_version_from_map_matches_expected_algorithm() -> None:
    """Version uses sha256 of canonical key-sorted JSON."""
    data = {"name": "test", "language": "python"}
    expected = hashlib.sha256(
        json.dumps(data, sort_keys=True).encode()
    ).hexdigest()
    assert profile_version_from_map(data) == expected


def test_legacy_json_and_rewritten_yaml_produce_same_version(tmp_path: Path) -> None:
    """P0 regression: JSON-shaped legacy profile.yaml and its canonically
    rewritten YAML equivalent must resolve to the same profile_version."""
    data = {
        "name": "omg-project",
        "preferences": {"constraints": {"api_cost": "minimize"}},
        "user_vector": {"tags": ["reliability"]},
    }
    # Write as JSON (legacy bug)
    json_path = tmp_path / "json-profile.yaml"
    json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Write as canonical YAML via profile_io
    yaml_path = tmp_path / "yaml-profile.yaml"
    save_profile(str(yaml_path), data)

    # Load both
    json_loaded = load_profile(str(json_path))
    yaml_loaded = load_profile(str(yaml_path))

    # Versions must match because same parsed dict
    assert profile_version_from_map(json_loaded) == profile_version_from_map(yaml_loaded)
