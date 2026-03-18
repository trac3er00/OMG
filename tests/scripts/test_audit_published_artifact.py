"""Tests for scripts/audit-published-artifact.py — published artifact self-audit gate."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "audit-published-artifact.py"

# Import the script module via importlib to avoid filename-with-hyphens issues
_spec = importlib.util.spec_from_file_location("audit_published_artifact", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_audit = _mod.run_audit
check_package_json_version = _mod.check_package_json_version
check_canonical_version = _mod.check_canonical_version
check_changelog_section = _mod.check_changelog_section
check_install_verification_index = _mod.check_install_verification_index
check_host_list_parity = _mod.check_host_list_parity
check_install_path_hygiene = _mod.check_install_path_hygiene


class TestHappyPath:
    """Run against the real repo root with the current CANONICAL_VERSION."""

    def test_audit_passes_against_repo_root(self) -> None:
        from runtime.adoption import CANONICAL_VERSION
        report = run_audit(ROOT, CANONICAL_VERSION)
        # package_json, canonical_version, changelog, host_list, install_path should all pass
        # cli_version_output may skip if node is not available
        for name, result in report["checks"].items():
            status = result.get("status")
            assert status in ("ok", "skip"), (
                f"Check {name} failed: {result}"
            )
        assert report["overall_status"] == "ok", f"Blockers: {report['blockers']}"

    def test_report_schema(self) -> None:
        from runtime.adoption import CANONICAL_VERSION
        report = run_audit(ROOT, CANONICAL_VERSION)
        assert report["schema"] == "ArtifactSelfAudit"
        assert report["version_expected"] == CANONICAL_VERSION
        assert "checks" in report
        assert "overall_status" in report
        assert "blockers" in report
        assert "timestamp" in report


class TestVersionMismatch:
    """Fake version 99.99.99 — all checks should report drift."""

    def test_package_json_mismatch(self) -> None:
        result = check_package_json_version(ROOT, "99.99.99")
        assert result["status"] == "fail"

    def test_canonical_version_mismatch(self) -> None:
        result = check_canonical_version(ROOT, "99.99.99")
        assert result["status"] == "fail"

    def test_changelog_section_missing(self) -> None:
        result = check_changelog_section(ROOT, "99.99.99")
        assert result["status"] == "fail"

    def test_install_verification_index_mismatch(self) -> None:
        result = check_install_verification_index(ROOT, "99.99.99")
        assert result["status"] == "fail"


class TestChangelogDetection:

    def test_detects_missing_changelog(self, tmp_path: Path) -> None:
        result = check_changelog_section(tmp_path, "1.0.0")
        assert result["status"] == "fail"
        assert "not found" in result["details"]

    def test_detects_missing_header(self, tmp_path: Path) -> None:
        (tmp_path / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 1.0.0 - 2026-01-01\n\n- initial\n",
            encoding="utf-8",
        )
        result = check_changelog_section(tmp_path, "2.0.0")
        assert result["status"] == "fail"
        assert "version header" in result["details"]

    def test_passes_with_header_and_marker(self, tmp_path: Path) -> None:
        (tmp_path / "CHANGELOG.md").write_text(
            "# Changelog\n\n<!-- OMG:GENERATED:changelog-v1.0.0 -->\n"
            "## 1.0.0 - 2026-01-01\n\n- initial\n"
            "<!-- /OMG:GENERATED:changelog-v1.0.0 -->\n",
            encoding="utf-8",
        )
        result = check_changelog_section(tmp_path, "1.0.0")
        assert result["status"] == "ok"


class TestHostListParity:

    def test_detects_missing_host_in_support_matrix(self, tmp_path: Path) -> None:
        (tmp_path / "SUPPORT-MATRIX.md").write_text(
            "# Support\n\n| Host |\n| claude |\n| codex |\n",
            encoding="utf-8",
        )
        (tmp_path / "INSTALL-VERIFICATION-INDEX.md").write_text(
            "claude codex gemini kimi opencode\n",
            encoding="utf-8",
        )
        result = check_host_list_parity(tmp_path)
        # Support matrix is missing gemini, kimi, opencode
        assert result["status"] == "fail"
        assert len(result["drift"]) > 0


class TestInstallPathHygiene:

    def test_clean_docs_pass(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "Use OMG-setup.sh to install.\n",
            encoding="utf-8",
        )
        result = check_install_path_hygiene(tmp_path)
        assert result["status"] == "ok"

    def test_bare_install_sh_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "Run install.sh to get started.\n",
            encoding="utf-8",
        )
        result = check_install_path_hygiene(tmp_path)
        assert result["status"] == "fail"
        assert len(result["stale_references"]) > 0


class TestFullAuditReport:

    def test_overall_fail_when_version_wrong(self) -> None:
        report = run_audit(ROOT, "99.99.99")
        assert report["overall_status"] == "fail"
        assert len(report["blockers"]) > 0

    def test_overall_pass_with_correct_version(self) -> None:
        from runtime.adoption import CANONICAL_VERSION
        report = run_audit(ROOT, CANONICAL_VERSION)
        assert report["overall_status"] == "ok"
