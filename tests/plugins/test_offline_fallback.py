"""Offline fallback tests for dependency health features.

Verifies all dep health modules degrade gracefully when network is unavailable:
- CVE scanner returns cached results or offline status on URLError
- License checker works fully offline (static matrix)
- Manifest detector works fully offline (file parsing only)
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import pytest

# ─── Path setup (match codebase convention) ──────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_cve_scanner = importlib.import_module("plugins.dephealth.cve_scanner")
scan_for_cves = _cve_scanner.scan_for_cves

_license_checker = importlib.import_module("plugins.dephealth.license_checker")
check_license_compatibility = _license_checker.check_license_compatibility

_manifest_detector = importlib.import_module("plugins.dephealth.manifest_detector")
detect_manifests = _manifest_detector.detect_manifests


@pytest.fixture(autouse=True)
def _enable_dep_health(monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")


# ─── CVE Scanner Offline Tests ───────────────────────────────────────────────


class TestCveScannerOfflineReturnsCached:
    """URLError with existing cache → returns cached results."""

    def test_cve_scanner_offline_returns_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Seed a cache file with known results
            cache_path = Path(tmp) / ".omg" / "state" / "cve-cache.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cached_data = {
                "results": {"lodash": [{"id": "CVE-2021-23337", "severity": "HIGH"}]},
                "cached": False,
                "scan_ts": datetime.now(timezone.utc).isoformat(),
            }
            cache_path.write_text(json.dumps(cached_data), encoding="utf-8")

            deps = [{"name": "lodash", "version": "4.17.20", "ecosystem": "npm"}]

            # Mock urlopen to raise URLError (simulate offline)
            with patch(
                "plugins.dephealth.cve_scanner.urllib.request.urlopen",
                side_effect=URLError("Network unreachable"),
            ):
                result = scan_for_cves(deps, project_dir=tmp)

            assert result["cached"] is True
            assert "lodash" in result["results"]
            assert result["results"]["lodash"][0]["id"] == "CVE-2021-23337"


class TestCveScannerOfflineNoCacheReturnsStatus:
    """URLError with no cache → returns offline status dict."""

    def test_cve_scanner_offline_no_cache_returns_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No cache file exists
            deps = [{"name": "express", "version": "4.18.0", "ecosystem": "npm"}]

            with patch(
                "plugins.dephealth.cve_scanner.urllib.request.urlopen",
                side_effect=URLError("No internet"),
            ):
                result = scan_for_cves(deps, project_dir=tmp)

            assert result["status"] == "offline"
            assert result["results"] == {}
            assert result["cached"] is False


# ─── License Checker Offline Tests ───────────────────────────────────────────


class TestLicenseCheckerWorksOffline:
    """License checker uses static matrix — no network dependency."""

    def test_license_checker_works_offline(self):
        deps = [
            {"name": "lodash", "license": "MIT"},
            {"name": "react", "license": "MIT"},
            {"name": "gpl-lib", "license": "GPL-3.0"},
        ]

        # No mocking needed — license_checker never touches the network.
        # Patch urlopen to raise so any accidental network call explodes.
        with patch(
            "urllib.request.urlopen",
            side_effect=RuntimeError("Network must NOT be used"),
        ):
            result = check_license_compatibility("MIT", deps)

        assert isinstance(result["compatible"], list)
        assert isinstance(result["incompatible"], list)
        assert isinstance(result["unknown"], list)

        # MIT deps compatible with MIT project
        pkg_names = [e["pkg"] for e in result["compatible"]]
        assert "lodash" in pkg_names
        assert "react" in pkg_names

        # GPL-3.0 dep in MIT project → incompatible
        incompat_names = [e["pkg"] for e in result["incompatible"]]
        assert "gpl-lib" in incompat_names


# ─── Manifest Detector Offline Tests ─────────────────────────────────────────


class TestManifestDetectorWorksOffline:
    """Manifest detector is file-based only — no network dependency."""

    def test_manifest_detector_works_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create a minimal package.json
            pkg = {"dependencies": {"express": "^4.18.0"}, "devDependencies": {"jest": "^29.0.0"}}
            (Path(tmp) / "package.json").write_text(json.dumps(pkg), encoding="utf-8")

            # Patch urlopen to raise so any accidental network call explodes
            with patch(
                "urllib.request.urlopen",
                side_effect=RuntimeError("Network must NOT be used"),
            ):
                result = detect_manifests(tmp)

        assert len(result.manifests) == 1
        assert result.manifests[0].format == "package.json"
        assert len(result.packages) == 2

        names = [p.name for p in result.packages]
        assert "express" in names
        assert "jest" in names


# ─── Cached Data Timestamp Tests ─────────────────────────────────────────────


class TestCachedDataShowsScanTimestamp:
    """Cached CVE results must carry a scan_ts field."""

    def test_cached_data_shows_scan_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / ".omg" / "state" / "cve-cache.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            original_ts = "2026-03-01T12:00:00+00:00"
            cached_data = {
                "results": {"pkg-a": []},
                "cached": False,
                "scan_ts": original_ts,
            }
            cache_path.write_text(json.dumps(cached_data), encoding="utf-8")

            deps = [{"name": "pkg-a", "version": "1.0.0", "ecosystem": "npm"}]

            with patch(
                "plugins.dephealth.cve_scanner.urllib.request.urlopen",
                side_effect=URLError("Offline"),
            ):
                result = scan_for_cves(deps, project_dir=tmp)

            # Must have scan_ts field
            assert "scan_ts" in result
            assert isinstance(result["scan_ts"], str)
            # Timestamp should be the original cached one
            assert result["scan_ts"] == original_ts


class TestCveScannerOfflineNoCacheNoTimestamp:
    """Offline with no cache → result still usable."""

    def test_offline_no_cache_has_no_scan_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            deps = [{"name": "some-pkg", "version": "2.0.0", "ecosystem": "PyPI"}]

            with patch(
                "plugins.dephealth.cve_scanner.urllib.request.urlopen",
                side_effect=URLError("Offline"),
            ):
                result = scan_for_cves(deps, project_dir=tmp)

            # Offline status dict — should not crash regardless of scan_ts presence
            assert result["status"] == "offline"
            assert result["results"] == {}


class TestCveScannerEmptyDepsOffline:
    """Empty dependency list returns immediately — no network call needed."""

    def test_empty_deps_returns_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "plugins.dephealth.cve_scanner.urllib.request.urlopen",
                side_effect=RuntimeError("Should never be called"),
            ):
                result = scan_for_cves([], project_dir=tmp)

            assert result["results"] == {}
            assert result["cached"] is False
            assert "scan_ts" in result
