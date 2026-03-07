from __future__ import annotations

from pathlib import Path

import yaml

from runtime.runtime_profile import load_runtime_profile, resolve_parallel_workers


def test_load_runtime_profile_defaults_to_balanced(tmp_path: Path):
    result = load_runtime_profile(str(tmp_path))
    assert result["profile"] == "balanced"
    assert result["max_workers"] == 3


def test_resolve_parallel_workers_respects_profile_and_cli_caps(tmp_path: Path):
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omg" / "runtime.yaml").write_text("profile: eco\n", encoding="utf-8")
    (omg_state / "cli-config.yaml").write_text(
        yaml.safe_dump(
            {
                "cli_configs": {
                    "codex": {"max_parallel_agents": 4},
                    "gemini": {"max_parallel_agents": 1},
                }
            }
        ),
        encoding="utf-8",
    )

    assert resolve_parallel_workers(str(tmp_path), requested_workers=5) == 1
