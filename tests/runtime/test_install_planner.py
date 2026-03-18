from __future__ import annotations

import importlib
from pathlib import Path


install_planner = importlib.import_module("runtime.install_planner")
compute_install_plan = install_planner.compute_install_plan
execute_plan = install_planner.execute_plan
normalize_detected_clis = install_planner.normalize_detected_clis


def _selected_servers() -> dict[str, dict[str, object]]:
    return {
        "filesystem": {
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem@2026.1.14", "."],
        },
        "omg-control": {
            "command": "python3",
            "args": ["-m", "runtime.omg_mcp_server"],
        },
    }


def test_compute_install_plan_returns_actions_without_writing_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    plan = compute_install_plan(
        project_dir=str(project_dir),
        detected_clis={"codex": {"detected": True}, "gemini": {"detected": False}},
        preset="safe",
        mode="focused",
        selected_ids=["filesystem", "omg-control"],
        selected_servers=_selected_servers(),
        source_root=tmp_path,
    )

    assert plan.actions
    assert (project_dir / ".mcp.json").exists() is False
    assert (tmp_path / "home" / ".codex" / "config.toml").exists() is False


def test_execute_plan_dry_run_returns_not_executed_and_preserves_disk(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    plan = compute_install_plan(
        project_dir=str(project_dir),
        detected_clis={"codex": {"detected": True}},
        preset="safe",
        mode="focused",
        selected_ids=["filesystem", "omg-control"],
        selected_servers=_selected_servers(),
        source_root=tmp_path,
    )

    result = execute_plan(plan, dry_run=True)

    assert result["executed"] is False
    assert result["errors"] == []
    assert (project_dir / ".mcp.json").exists() is False
    assert (tmp_path / "home" / ".codex" / "config.toml").exists() is False


def test_execute_plan_runs_integrity_precheck_before_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "OMG-setup.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (source_root / "INSTALL_INTEGRITY.sha256").write_text(
        "0000000000000000000000000000000000000000000000000000000000000000  OMG-setup.sh\n",
        encoding="utf-8",
    )

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    plan = compute_install_plan(
        project_dir=str(project_dir),
        detected_clis={},
        preset="safe",
        mode="focused",
        selected_ids=["filesystem", "omg-control"],
        selected_servers=_selected_servers(),
        source_root=source_root,
    )

    result = execute_plan(plan, dry_run=False)

    assert result["executed"] is False
    assert any("integrity" in error.lower() for error in result["errors"])
    assert (project_dir / ".mcp.json").exists() is False


def test_compute_install_plan_has_separate_actions_for_detected_hosts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    plan = compute_install_plan(
        project_dir=str(project_dir),
        detected_clis={
            "codex": {"detected": True},
            "gemini": {"detected": True},
            "kimi": {"detected": True},
            "opencode": {"detected": True},
        },
        preset="safe",
        mode="focused",
        selected_ids=["filesystem", "omg-control"],
        selected_servers=_selected_servers(),
        source_root=tmp_path,
    )

    hosts = [action.host for action in plan.actions]
    assert "claude" in hosts
    assert "codex" in hosts
    assert "gemini" in hosts
    assert "kimi" in hosts
    assert "opencode" in hosts


get_owned_install_paths = install_planner.get_owned_install_paths


def test_get_owned_install_paths_returns_known_config_paths(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    paths = get_owned_install_paths(str(project_dir))

    assert isinstance(paths, list)
    assert len(paths) > 0
    joined = " ".join(paths)
    assert ".codex" in joined
    assert ".gemini" in joined
    assert ".kimi" in joined
    assert ".config/opencode" in joined
    assert ".mcp.json" in joined
    assert ".claude" in joined


def test_normalize_detected_clis_derives_configured_state_from_host_configs(tmp_path: Path) -> None:
    home = tmp_path / "home"
    gemini_config = home / ".gemini" / "settings.json"
    gemini_config.parent.mkdir(parents=True)
    gemini_config.write_text("{}\n", encoding="utf-8")

    normalized = normalize_detected_clis(
        {
            "gemini": {"detected": False},
            "codex": {"detected": True},
        },
        home_path=home,
    )

    assert normalized["gemini"]["detected"] is False
    assert normalized["gemini"]["configured"] is True
    assert normalized["codex"]["detected"] is True
    assert normalized["codex"]["configured"] is False
    assert normalized["kimi"]["detected"] is False


def test_normalize_detected_clis_derives_opencode_configured_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    opencode_config = home / ".config" / "opencode" / "opencode.json"
    opencode_config.parent.mkdir(parents=True)
    opencode_config.write_text("{}\n", encoding="utf-8")

    normalized = normalize_detected_clis(
        {
            "opencode": {"detected": False},
        },
        home_path=home,
    )

    assert normalized["opencode"]["detected"] is False
    assert normalized["opencode"]["configured"] is True
