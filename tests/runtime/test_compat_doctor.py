"""Tests for orphaned_runtime doctor check and fix handler."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runtime.compat import (
    DOCTOR_FIX_SPECS,
    _check_orphaned_runtime,
    _collect_orphaned_runtime_refs,
    run_doctor,
    run_doctor_fix,
)


def _make_settings_with_orphan_hook(claude_dir: Path) -> None:
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "command": str(claude_dir / "omg-runtime" / ".venv" / "bin" / "python"),
                    "args": ["-m", "runtime.firewall"],
                }
            ]
        }
    }
    (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _make_mcp_json_with_orphan(claude_dir: Path) -> None:
    mcp = {
        "mcpServers": {
            "omg-control": {
                "command": str(claude_dir / "omg-runtime" / ".venv" / "bin" / "python"),
                "args": ["-m", "runtime.omg_mcp_server"],
            }
        }
    }
    (claude_dir / ".mcp.json").write_text(json.dumps(mcp, indent=2), encoding="utf-8")


def test_orphaned_runtime_check_blocker_when_dangling_hook(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_settings_with_orphan_hook(claude_dir)

    check = _check_orphaned_runtime(str(claude_dir), home_dir=str(tmp_path))
    assert check["name"] == "orphaned_runtime"
    assert check["status"] == "warning", f"expected warning, got: {check}"
    assert "omg-runtime" in check["message"]
    assert check["required"] is False


def test_orphaned_runtime_check_ok_when_no_references(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    clean_settings = {"hooks": {"PreToolUse": [{"command": "/usr/bin/python3", "args": []}]}}
    (claude_dir / "settings.json").write_text(json.dumps(clean_settings), encoding="utf-8")

    check = _check_orphaned_runtime(str(claude_dir), home_dir=str(tmp_path))
    assert check["name"] == "orphaned_runtime"
    assert check["status"] == "ok"
    assert check["required"] is False


def test_orphaned_runtime_check_ok_when_runtime_present(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    venv_bin = claude_dir / "omg-runtime" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    python_bin = venv_bin / "python"
    python_bin.write_text("#!/bin/sh\nexec python3 \"$@\"\n", encoding="utf-8")

    _make_settings_with_orphan_hook(claude_dir)

    check = _check_orphaned_runtime(str(claude_dir), home_dir=str(tmp_path))
    assert check["name"] == "orphaned_runtime"
    assert check["status"] == "ok"


def test_orphaned_runtime_check_blocker_when_mcp_json_dangling(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_mcp_json_with_orphan(claude_dir)

    check = _check_orphaned_runtime(str(claude_dir), home_dir=str(tmp_path))
    assert check["name"] == "orphaned_runtime"
    assert check["status"] == "warning"
    assert "omg-runtime" in check["message"]


def test_collect_orphaned_runtime_refs_returns_list(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_settings_with_orphan_hook(claude_dir)

    refs = _collect_orphaned_runtime_refs(str(claude_dir), home_dir=str(tmp_path))
    assert isinstance(refs, list)
    assert len(refs) >= 1
    assert any("omg-runtime" in r for r in refs)


def test_collect_orphaned_runtime_refs_empty_when_clean(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    refs = _collect_orphaned_runtime_refs(str(claude_dir), home_dir=str(tmp_path))
    assert refs == []


def test_run_doctor_includes_orphaned_runtime_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor(root_dir=tmp_path)
    check_names = {c["name"] for c in result["checks"]}
    assert "orphaned_runtime" in check_names


def test_run_doctor_orphaned_runtime_is_optional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor(root_dir=tmp_path)
    orphan_checks = [c for c in result["checks"] if c["name"] == "orphaned_runtime"]
    assert len(orphan_checks) == 1
    assert orphan_checks[0]["required"] is False


def test_run_doctor_orphaned_runtime_warning_does_not_cause_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_settings_with_orphan_hook(claude_dir)
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor(root_dir=tmp_path)
    orphan_checks = [c for c in result["checks"] if c["name"] == "orphaned_runtime"]
    assert orphan_checks[0]["status"] in {"warning", "ok"}
    assert orphan_checks[0]["status"] != "blocker"


def test_doctor_fix_specs_has_orphaned_runtime_entry() -> None:
    assert "orphaned_runtime" in DOCTOR_FIX_SPECS
    spec = DOCTOR_FIX_SPECS["orphaned_runtime"]
    assert spec["fixable"] is True
    assert spec["fix_handler"] is not None
    assert spec["fixable_in_context"] is True


def test_run_doctor_fix_orphaned_runtime_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_settings_with_orphan_hook(claude_dir)
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor_fix(root_dir=tmp_path, dry_run=True)
    assert result["schema"] == "DoctorFixResult"
    assert result["mode"] == "dry_run"

    orphan_receipts = [r for r in result["fix_receipts"] if r["check"] == "orphaned_runtime"]
    assert len(orphan_receipts) == 1
    receipt = orphan_receipts[0]
    assert receipt["action"] == "remove_orphaned_runtime"
    assert receipt["executed"] is False
    assert "verification" in receipt
    assert "backup_path" in receipt

    settings_after = json.loads((claude_dir / "settings.json").read_text())
    hooks_after = settings_after.get("hooks", {}).get("PreToolUse", [])
    assert any("omg-runtime" in str(h) for h in hooks_after), "dry_run should not remove hooks"


def test_run_doctor_fix_orphaned_runtime_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_settings_with_orphan_hook(claude_dir)
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor_fix(root_dir=tmp_path, dry_run=False)
    assert result["schema"] == "DoctorFixResult"
    assert result["mode"] == "fix"

    orphan_receipts = [r for r in result["fix_receipts"] if r["check"] == "orphaned_runtime"]
    assert len(orphan_receipts) == 1
    receipt = orphan_receipts[0]
    assert receipt["action"] == "remove_orphaned_runtime"
    assert receipt["executed"] is True


def test_run_doctor_fix_clean_install_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor_fix(root_dir=tmp_path, dry_run=False)
    orphan_receipts = [r for r in result["fix_receipts"] if r["check"] == "orphaned_runtime"]
    assert len(orphan_receipts) == 0
