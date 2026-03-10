from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import importlib.util

_SCRIPT_PATH = _REPO_ROOT / "scripts" / "validate-release-identity.py"
_spec = importlib.util.spec_from_file_location("validate_release_identity", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

validate_authored = _mod.validate_authored
validate_derived = _mod.validate_derived
scan_scoped_residue = _mod.scan_scoped_residue
build_report = _mod.build_report

_OLD_VERSION = "0.0.1-test"


class TestHappyPath:
    def test_exits_zero_on_clean_tree(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "all", "--forbid-version", _OLD_VERSION],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["overall_status"] == "ok"
        assert result.returncode == 0

    def test_json_output_structure(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "all"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert "canonical_version" in output
        assert "scope" in output
        assert "authored" in output
        assert "derived" in output
        assert "overall_status" in output
        assert output["scope"] == "all"


class TestAuthoredDrift:
    def test_authored_blockers_on_drift(self):
        with patch.object(_mod, "check_surface") as mock_check:
            mock_check.return_value = [("package.json version", "1.0.0")]
            result = validate_authored(_REPO_ROOT, _OLD_VERSION)
        assert result["status"] == "fail"
        assert len(result["blockers"]) > 0
        blocker = result["blockers"][0]
        assert blocker["surface"] == "package.json version"
        assert blocker["found"] == "1.0.0"
        assert blocker["expected"] == _OLD_VERSION

    def test_authored_ok_when_no_drift(self):
        with patch.object(_mod, "check_surface") as mock_check:
            mock_check.return_value = []
            result = validate_authored(_REPO_ROOT, _OLD_VERSION)
        assert result["status"] == "ok"
        assert result["blockers"] == []


class TestDerivedDrift:
    def test_derived_blockers_on_mismatch(self, tmp_path):
        manifest_dir = tmp_path / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text(json.dumps({"contract_version": "1.0.0"}))

        result = validate_derived(tmp_path, _OLD_VERSION)
        assert result["status"] == "fail"
        assert any(b["surface"].endswith("manifest.json") for b in result["blockers"])

    def test_derived_ok_when_version_matches(self, tmp_path):
        manifest_dir = tmp_path / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text(json.dumps({"contract_version": _OLD_VERSION}))

        result = validate_derived(tmp_path, _OLD_VERSION)
        matching = [b for b in result["blockers"] if "dist/public/manifest.json" in b["surface"]]
        assert matching == []


class TestScopedResidue:
    def test_residue_detected_in_file(self, tmp_path):
        target = tmp_path / "dist" / "public" / "manifest.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"contract_version": _OLD_VERSION, "name": "test"}))

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        assert result["status"] == "fail"
        assert len(result["blockers"]) > 0

    def test_residue_detected_in_directory(self, tmp_path):
        bundle_dir = tmp_path / "dist" / "public" / "bundle"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "index.js").write_text(f'const VERSION = "{_OLD_VERSION}";')

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        assert result["status"] == "fail"
        assert any("index.js" in b["file"] for b in result["blockers"])

    def test_residue_clean_when_no_forbidden(self, tmp_path):
        target = tmp_path / "dist" / "public" / "manifest.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"contract_version": "3.0.0", "name": "test"}')

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        matching = [b for b in result["blockers"] if "dist/public/manifest.json" in b["file"]]
        assert matching == []

    def test_changelog_historical_excluded(self, tmp_path):
        release_dir = tmp_path / "artifacts" / "release"
        release_dir.mkdir(parents=True)
        (release_dir / "CHANGELOG.md").write_text(f"## [{_OLD_VERSION}] - 2025-01-01\n- old entry\n")

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        changelog_blockers = [
            b for b in result["blockers"]
            if b["file"].endswith("CHANGELOG.md") and f"## [{_OLD_VERSION}]" in b["content"]
        ]
        assert changelog_blockers == []


class TestMissingDerived:
    def test_missing_files_not_error(self, tmp_path):
        result = validate_derived(tmp_path, _OLD_VERSION)
        assert result["status"] == "ok"
        assert result["blockers"] == []


class TestOutputFormat:
    def test_build_report_structure(self):
        report = build_report(
            canonical=_OLD_VERSION,
            scope="all",
            forbid_version=_OLD_VERSION,
            authored={"status": "ok", "blockers": []},
            derived={"status": "ok", "blockers": []},
            scoped_residue={"status": "ok", "forbid_version": _OLD_VERSION, "blockers": []},
        )
        assert report["canonical_version"] == _OLD_VERSION
        assert report["scope"] == "all"
        assert report["forbid_version"] == _OLD_VERSION
        assert report["overall_status"] == "ok"

    def test_build_report_fail_on_any_blocker(self):
        report = build_report(
            canonical=_OLD_VERSION,
            scope="all",
            forbid_version=None,
            authored={"status": "fail", "blockers": [{"surface": "x", "found": "1.0", "expected": _OLD_VERSION}]},
            derived={"status": "ok", "blockers": []},
            scoped_residue=None,
        )
        assert report["overall_status"] == "fail"


class TestScopeAuthored:
    def test_scope_authored_subprocess(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "authored"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["scope"] == "authored"
        assert "authored" in output
        assert output.get("derived") is None or output["derived"]["status"] == "skipped"


class TestScopeDerived:
    def test_scope_derived_subprocess(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "derived"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["scope"] == "derived"
        assert output.get("authored") is None or output["authored"]["status"] == "skipped"
        assert "derived" in output
