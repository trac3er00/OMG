from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "omg.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("omg_cli", str(SCRIPT))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()


def test_release_audit_subcommand_is_registered() -> None:
    parser = _mod.build_parser()
    args = parser.parse_args(["release", "audit", "--artifact"])

    assert args.command == "release"
    assert args.func == _mod.cmd_release_audit
    assert args.artifact is True


def test_cmd_release_audit_json_delegates_to_engine(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    expected = {
        "status": "ok",
        "schema": "ReleaseArtifactAudit",
        "overall_status": "ok",
        "version": "2.2.12",
        "repo": "trac3r00/OMG",
    }

    def _fake_run_release_artifact_audit(*args, **kwargs):
        return expected

    monkeypatch.setattr(_mod, "run_release_artifact_audit", _fake_run_release_artifact_audit)
    args = Namespace(
        artifact=True,
        apply=False,
        confirm="",
        repo="trac3r00/OMG",
        version="",
        format="json",
        output_json="",
    )

    rc = _mod.cmd_release_audit(args)
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out == expected


def test_cmd_ship_blocks_on_release_audit_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    idea_path = tmp_path / "idea.json"
    idea_path.write_text(json.dumps({"goal": "ship it"}), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    def _fake_release_audit(*args, **kwargs):
        return {
            "status": "ok",
            "schema": "ReleaseArtifactAudit",
            "overall_status": "fail",
            "blockers": ["github_release_missing:v2.2.12"],
            "verdict": "FAIL",
        }

    def _fail_dispatch(*args, **kwargs):
        raise AssertionError("dispatch_runtime should not run when release audit drifts")

    monkeypatch.setattr(_mod, "run_release_artifact_audit", _fake_release_audit)
    monkeypatch.setattr(_mod, "dispatch_runtime", _fail_dispatch)

    rc = _mod.cmd_ship(Namespace(idea=str(idea_path), runtime="local", run_id=""))
    out = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert out["status"] == "error"
    assert out["error_code"] == "RELEASE_AUDIT_BLOCKED"
