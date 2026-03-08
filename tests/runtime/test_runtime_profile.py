from __future__ import annotations

from pathlib import Path

import yaml

import pytest

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
