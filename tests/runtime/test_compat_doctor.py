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


# --- OpenCode and Codex residue tests ---


def _make_opencode_with_orphan(home_dir: Path, claude_dir: Path) -> Path:
    oc_dir = home_dir / ".config" / "opencode"
    oc_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "mcp": {
            "omg-control": {
                "command": str(claude_dir / "omg-runtime" / ".venv" / "bin" / "python"),
                "args": ["-m", "runtime.omg_mcp_server"],
            }
        }
    }
    cfg_path = oc_dir / "opencode.json"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg_path


def _make_codex_toml_with_orphan(home_dir: Path, claude_dir: Path) -> Path:
    codex_dir = home_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    toml_content = (
        '[mcp_servers.omg-control]\n'
        f'command = "{claude_dir / "omg-runtime" / ".venv" / "bin" / "python"}"\n'
        'args = ["-m", "runtime.omg_mcp_server"]\n'
    )
    cfg_path = codex_dir / "config.toml"
    cfg_path.write_text(toml_content, encoding="utf-8")
    return cfg_path


def test_collect_orphaned_runtime_refs_detects_opencode_residue(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_opencode_with_orphan(tmp_path, claude_dir)

    refs = _collect_orphaned_runtime_refs(str(claude_dir), home_dir=str(tmp_path))
    assert any("opencode" in r for r in refs), f"OpenCode residue not detected: {refs}"


def test_collect_orphaned_runtime_refs_detects_codex_toml_residue(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    _make_codex_toml_with_orphan(tmp_path, claude_dir)

    refs = _collect_orphaned_runtime_refs(str(claude_dir), home_dir=str(tmp_path))
    assert any("codex" in r for r in refs), f"Codex TOML residue not detected: {refs}"


def test_collect_orphaned_runtime_refs_detects_codex_toml_when_runtime_dir_exists_but_python_missing(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    (claude_dir / "omg-runtime").mkdir(parents=True)
    _make_codex_toml_with_orphan(tmp_path, claude_dir)

    refs = _collect_orphaned_runtime_refs(str(claude_dir), home_dir=str(tmp_path))
    assert any("codex" in r for r in refs), f"Codex broken-venv residue not detected: {refs}"


def test_fix_orphaned_runtime_removes_opencode_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    oc_cfg = _make_opencode_with_orphan(tmp_path, claude_dir)
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor_fix(root_dir=tmp_path, dry_run=False)
    orphan_receipts = [r for r in result["fix_receipts"] if r["check"] == "orphaned_runtime"]
    assert len(orphan_receipts) == 1
    assert orphan_receipts[0]["executed"] is True

    data = json.loads(oc_cfg.read_text())
    assert "omg-control" not in data.get("mcp", {}), "OpenCode omg-control should be removed"


def test_fix_orphaned_runtime_removes_codex_toml_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    codex_cfg = _make_codex_toml_with_orphan(tmp_path, claude_dir)
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor_fix(root_dir=tmp_path, dry_run=False)
    orphan_receipts = [r for r in result["fix_receipts"] if r["check"] == "orphaned_runtime"]
    assert len(orphan_receipts) == 1
    assert orphan_receipts[0]["executed"] is True

    content = codex_cfg.read_text()
    assert "omg-control" not in content, "Codex omg-control should be removed from TOML"


def test_fix_orphaned_runtime_removes_codex_toml_when_runtime_dir_exists_but_python_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    claude_dir = tmp_path / ".claude"
    (claude_dir / "omg-runtime").mkdir(parents=True)
    codex_cfg = _make_codex_toml_with_orphan(tmp_path, claude_dir)
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor_fix(root_dir=tmp_path, dry_run=False)
    orphan_receipts = [r for r in result["fix_receipts"] if r["check"] == "orphaned_runtime"]
    assert len(orphan_receipts) == 1
    assert orphan_receipts[0]["executed"] is True

    content = codex_cfg.read_text()
    assert "omg-control" not in content, "Codex omg-control should be removed when managed python is missing"


def test_fix_orphaned_runtime_dry_run_preserves_codex_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    codex_cfg = _make_codex_toml_with_orphan(tmp_path, claude_dir)
    monkeypatch.setenv("CLAUDE_DIR", str(claude_dir))
    monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))

    result = run_doctor_fix(root_dir=tmp_path, dry_run=True)
    orphan_receipts = [r for r in result["fix_receipts"] if r["check"] == "orphaned_runtime"]
    assert len(orphan_receipts) == 1
    assert orphan_receipts[0]["executed"] is False

    content = codex_cfg.read_text()
    assert "omg-control" in content, "dry_run should preserve Codex TOML"


# --- env doctor tests ---


from runtime.compat import run_env_doctor


class TestEnvDoctor:
    """Tests for the env-doctor pack (run_env_doctor)."""

    def test_returns_doctor_result_schema(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        assert result["schema"] == "DoctorResult"
        assert result["status"] in ("pass", "fail")
        assert "checks" in result
        assert isinstance(result["checks"], list)
        assert "verdict_receipt" in result

    def test_includes_node_version_check(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        names = {c["name"] for c in result["checks"]}
        assert "node_version" in names

    def test_includes_python3_check(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        names = {c["name"] for c in result["checks"]}
        assert "python3_available" in names

    def test_includes_path_checks_for_host_clis(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        names = {c["name"] for c in result["checks"]}
        for cli in ("codex", "gemini", "kimi", "opencode"):
            assert f"{cli}_path" in names, f"missing {cli}_path check"

    def test_includes_claude_auth_non_probed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        claude_auth = [c for c in result["checks"] if c["name"] == "claude_auth"]
        assert len(claude_auth) == 1
        assert claude_auth[0]["status"] == "ok"
        assert "host-native/non-probed" in claude_auth[0]["message"]
        assert claude_auth[0]["required"] is False

    def test_all_checks_not_required(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        for check in result["checks"]:
            assert check["required"] is False, f"check {check['name']} has required=True"

    def test_checks_have_remediation_field(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        for check in result["checks"]:
            assert "remediation" in check, f"check {check['name']} missing remediation field"

    def test_includes_writable_dir_checks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        result = run_env_doctor(root_dir=tmp_path)
        names = {c["name"] for c in result["checks"]}
        writable_checks = [n for n in names if n.startswith("writable_")]
        assert len(writable_checks) >= 1, "expected at least one writable_* check"

    def test_includes_auth_checks_for_detected_clis(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Auth checks appear for each detected CLI provider."""
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        import shutil
        # Mock all CLIs as not on PATH so no auth checks fire (except claude)
        monkeypatch.setattr(shutil, "which", lambda name: None)
        result = run_env_doctor(root_dir=tmp_path)
        auth_names = [c["name"] for c in result["checks"] if c["name"].endswith("_auth")]
        # claude_auth should always be present
        assert "claude_auth" in auth_names
        # No other auth checks when CLIs are not on PATH
        non_claude_auth = [n for n in auth_names if n != "claude_auth"]
        assert len(non_claude_auth) == 0

    def test_node_check_warns_when_node_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Node check is warning when node is not on PATH."""
        monkeypatch.setenv("OMG_TEST_HOME_DIR", str(tmp_path))
        import shutil
        original_which = shutil.which
        monkeypatch.setattr(shutil, "which", lambda name: None if name == "node" else original_which(name))
        import subprocess
        original_run = subprocess.run
        def _block_node(cmd, **kwargs):
            if cmd and cmd[0] == "node":
                raise FileNotFoundError("node not found")
            return original_run(cmd, **kwargs)
        monkeypatch.setattr(subprocess, "run", _block_node)
        result = run_env_doctor(root_dir=tmp_path)
        node_check = next(c for c in result["checks"] if c["name"] == "node_version")
        assert node_check["status"] == "warning"
