"""Tests for license compatibility checker."""

import os
import pytest
from plugins.dephealth.license_checker import check_license_compatibility


@pytest.fixture(autouse=True)
def _enable_dep_health(monkeypatch):
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")


class TestGPLDepInMITProjectIncompatible:
    """GPL dependency in MIT project should be flagged as incompatible."""

    def test_gpl_dep_in_mit_project_incompatible(self):
        deps = [{"name": "some-gpl-lib", "license": "GPL-3.0"}]
        result = check_license_compatibility("MIT", deps)
        assert len(result["incompatible"]) == 1
        entry = result["incompatible"][0]
        assert entry["pkg"] == "some-gpl-lib"
        assert entry["license"] == "GPL-3.0"
        assert "reason" in entry
        assert len(result["compatible"]) == 0
        assert len(result["unknown"]) == 0

    def test_gpl2_dep_in_apache_project_incompatible(self):
        deps = [{"name": "gpl2-lib", "license": "GPL-2.0"}]
        result = check_license_compatibility("Apache-2.0", deps)
        assert len(result["incompatible"]) == 1
        assert result["incompatible"][0]["pkg"] == "gpl2-lib"


class TestMITDepInGPLProjectCompatible:
    """MIT dependency in GPL project should be compatible."""

    def test_mit_dep_in_gpl_project_compatible(self):
        deps = [{"name": "lodash", "license": "MIT"}]
        result = check_license_compatibility("GPL-3.0", deps)
        assert len(result["compatible"]) == 1
        assert result["compatible"][0]["pkg"] == "lodash"
        assert result["compatible"][0]["license"] == "MIT"
        assert len(result["incompatible"]) == 0

    def test_bsd_dep_in_gpl_project_compatible(self):
        deps = [{"name": "bsd-lib", "license": "BSD-3-Clause"}]
        result = check_license_compatibility("GPL-3.0", deps)
        assert len(result["compatible"]) == 1


class TestAGPLDepAlwaysIncompatible:
    """AGPL dependency should be flagged in any non-AGPL project."""

    def test_agpl_dep_in_mit_project(self):
        deps = [{"name": "agpl-lib", "license": "AGPL-3.0"}]
        result = check_license_compatibility("MIT", deps)
        assert len(result["incompatible"]) == 1
        assert result["incompatible"][0]["pkg"] == "agpl-lib"

    def test_agpl_dep_in_gpl_project(self):
        deps = [{"name": "agpl-lib", "license": "AGPL-3.0"}]
        result = check_license_compatibility("GPL-3.0", deps)
        assert len(result["incompatible"]) == 1

    def test_agpl_dep_in_apache_project(self):
        deps = [{"name": "agpl-lib", "license": "AGPL-3.0"}]
        result = check_license_compatibility("Apache-2.0", deps)
        assert len(result["incompatible"]) == 1

    def test_agpl_dep_in_agpl_project_compatible(self):
        deps = [{"name": "agpl-lib", "license": "AGPL-3.0"}]
        result = check_license_compatibility("AGPL-3.0", deps)
        assert len(result["compatible"]) == 1
        assert result["compatible"][0]["pkg"] == "agpl-lib"


class TestUnknownLicenseInUnknownList:
    """None or UNKNOWN license should go to unknown list."""

    def test_none_license(self):
        deps = [{"name": "mystery-pkg", "license": None}]
        result = check_license_compatibility("MIT", deps)
        assert len(result["unknown"]) == 1
        assert result["unknown"][0]["pkg"] == "mystery-pkg"
        assert len(result["compatible"]) == 0
        assert len(result["incompatible"]) == 0

    def test_unknown_string_license(self):
        deps = [{"name": "other-pkg", "license": "UNKNOWN"}]
        result = check_license_compatibility("MIT", deps)
        assert len(result["unknown"]) == 1
        assert result["unknown"][0]["pkg"] == "other-pkg"

    def test_empty_string_license(self):
        deps = [{"name": "empty-lic", "license": ""}]
        result = check_license_compatibility("MIT", deps)
        assert len(result["unknown"]) == 1


class TestPermissiveDepsAllCompatible:
    """MIT, BSD, ISC, Unlicense, CC0 should all be compatible in any project."""

    def test_permissive_deps_all_compatible(self):
        deps = [
            {"name": "mit-lib", "license": "MIT"},
            {"name": "bsd2-lib", "license": "BSD-2-Clause"},
            {"name": "bsd3-lib", "license": "BSD-3-Clause"},
            {"name": "isc-lib", "license": "ISC"},
            {"name": "unlicense-lib", "license": "Unlicense"},
            {"name": "cc0-lib", "license": "CC0-1.0"},
        ]
        result = check_license_compatibility("Apache-2.0", deps)
        assert len(result["compatible"]) == 6
        assert len(result["incompatible"]) == 0
        assert len(result["unknown"]) == 0

    def test_permissive_in_agpl_project(self):
        deps = [
            {"name": "mit-lib", "license": "MIT"},
            {"name": "isc-lib", "license": "ISC"},
        ]
        result = check_license_compatibility("AGPL-3.0", deps)
        assert len(result["compatible"]) == 2


class TestReturnsCorrectStructure:
    """Output must have compatible, incompatible, and unknown keys."""

    def test_returns_correct_structure(self):
        result = check_license_compatibility("MIT", [])
        assert "compatible" in result
        assert "incompatible" in result
        assert "unknown" in result
        assert isinstance(result["compatible"], list)
        assert isinstance(result["incompatible"], list)
        assert isinstance(result["unknown"], list)

    def test_mixed_deps_sorted_correctly(self):
        deps = [
            {"name": "ok-lib", "license": "MIT"},
            {"name": "bad-lib", "license": "GPL-3.0"},
            {"name": "mystery", "license": None},
        ]
        result = check_license_compatibility("MIT", deps)
        assert len(result["compatible"]) == 1
        assert len(result["incompatible"]) == 1
        assert len(result["unknown"]) == 1

    def test_incompatible_entry_has_reason(self):
        deps = [{"name": "gpl-lib", "license": "GPL-3.0"}]
        result = check_license_compatibility("MIT", deps)
        entry = result["incompatible"][0]
        assert "reason" in entry
        assert isinstance(entry["reason"], str)
        assert len(entry["reason"]) > 0


class TestApacheInGPLCompatibility:
    """Apache-2.0 dep in GPL-3.0 project should be compatible (one-way)."""

    def test_apache_dep_in_gpl3_project_compatible(self):
        deps = [{"name": "apache-lib", "license": "Apache-2.0"}]
        result = check_license_compatibility("GPL-3.0", deps)
        assert len(result["compatible"]) == 1

    def test_gpl_dep_in_apache_project_incompatible(self):
        deps = [{"name": "gpl-lib", "license": "GPL-3.0"}]
        result = check_license_compatibility("Apache-2.0", deps)
        assert len(result["incompatible"]) == 1


class TestWeakCopyleftDeps:
    """LGPL/MPL deps in permissive projects - weak copyleft rules."""

    def test_lgpl_dep_in_mit_compatible(self):
        """LGPL allows dynamic linking in permissive projects."""
        deps = [{"name": "lgpl-lib", "license": "LGPL-3.0"}]
        result = check_license_compatibility("MIT", deps)
        assert len(result["compatible"]) == 1

    def test_mpl_dep_in_mit_compatible(self):
        """MPL is file-level copyleft, compatible with permissive projects."""
        deps = [{"name": "mpl-lib", "license": "MPL-2.0"}]
        result = check_license_compatibility("MIT", deps)
        assert len(result["compatible"]) == 1
