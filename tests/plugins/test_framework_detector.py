"""Tests for plugins/testgen/framework_detector.py — detect_test_framework()."""
import json
import os
import sys
import tempfile

import pytest

# Add project root to sys.path for import
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from plugins.testgen.framework_detector import FrameworkInfo, detect_test_framework


class TestDetectJestFromPackageJson:
    """T1: jest in devDependencies → framework='jest'."""

    def test_detect_jest_from_package_json(self, tmp_path):
        pkg = {
            "devDependencies": {"jest": "^29.0.0", "@types/jest": "^29.0.0"},
            "scripts": {"test": "jest"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        result = detect_test_framework(str(tmp_path))

        assert isinstance(result, FrameworkInfo)
        assert result.framework == "jest"
        assert result.config_file == "package.json"
        assert result.assertion_style == "expect"
        assert result.mock_library == "jest.mock"


class TestDetectVitestFromPackageJson:
    """T2: vitest in devDependencies → framework='vitest'."""

    def test_detect_vitest_from_package_json(self, tmp_path):
        pkg = {
            "devDependencies": {"vitest": "^1.0.0"},
            "scripts": {"test": "vitest run"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "vitest"
        assert result.config_file == "package.json"
        assert result.assertion_style == "expect"
        assert result.mock_library == "vi.mock"


class TestDetectPytestFromPyprojectToml:
    """T3: pytest in pyproject.toml → framework='pytest'."""

    def test_detect_pytest_from_pyproject_toml(self, tmp_path):
        pyproject = '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        (tmp_path / "pyproject.toml").write_text(pyproject)

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "pytest"
        assert result.config_file == "pyproject.toml"
        assert result.test_dir == "tests"
        assert result.assertion_style == "assert"
        assert result.mock_library == "unittest.mock"


class TestDetectGoFromGoMod:
    """T4: go.mod present → framework='go test'."""

    def test_detect_go_from_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/mymod\n\ngo 1.21\n")

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "go test"
        assert result.config_file == "go.mod"
        assert result.assertion_style == "testing.T"
        assert result.mock_library == "testify/mock"


class TestDetectCargoFromCargoToml:
    """T5: Cargo.toml present → framework='cargo test'."""

    def test_detect_cargo_from_cargo_toml(self, tmp_path):
        cargo = '[package]\nname = "mylib"\nversion = "0.1.0"\n'
        (tmp_path / "Cargo.toml").write_text(cargo)

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "cargo test"
        assert result.config_file == "Cargo.toml"
        assert result.assertion_style == "assert!"
        assert result.mock_library == "mockall"


class TestDetectRspecFromGemfile:
    """T6: Gemfile with rspec → framework='rspec'."""

    def test_detect_rspec_from_gemfile(self, tmp_path):
        gemfile = "source 'https://rubygems.org'\n\ngem 'rspec'\ngem 'rails'\n"
        (tmp_path / "Gemfile").write_text(gemfile)

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "rspec"
        assert result.config_file == "Gemfile"
        assert result.assertion_style == "expect"
        assert result.mock_library == "rspec-mocks"


class TestUnknownFrameworkNoCrash:
    """T7: empty directory → framework='unknown', no crash."""

    def test_unknown_framework_no_crash(self, tmp_path):
        result = detect_test_framework(str(tmp_path))

        assert isinstance(result, FrameworkInfo)
        assert result.framework == "unknown"
        assert result.config_file == ""
        assert result.test_dir == ""
        assert result.assertion_style == ""
        assert result.mock_library == ""
        assert result.multi_framework == []


class TestMultiFrameworkDetection:
    """T8: both jest and playwright detected → multi_framework populated."""

    def test_multi_framework_detection(self, tmp_path):
        pkg = {
            "devDependencies": {
                "jest": "^29.0.0",
                "@playwright/test": "^1.40.0",
            },
            "scripts": {"test": "jest", "test:e2e": "playwright test"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "jest"  # primary
        assert "jest" in result.multi_framework
        assert "playwright" in result.multi_framework
        assert len(result.multi_framework) >= 2


class TestDetectPytestFromSetupCfg:
    """T9 (bonus): pytest detected from setup.cfg."""

    def test_detect_pytest_from_setup_cfg(self, tmp_path):
        setup_cfg = "[tool:pytest]\ntestpaths = tests\n"
        (tmp_path / "setup.cfg").write_text(setup_cfg)

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "pytest"
        assert result.config_file == "setup.cfg"


class TestDetectMochaFromPackageJson:
    """T10 (bonus): mocha in devDependencies → framework='mocha'."""

    def test_detect_mocha_from_package_json(self, tmp_path):
        pkg = {
            "devDependencies": {"mocha": "^10.0.0", "chai": "^4.0.0"},
            "scripts": {"test": "mocha"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        result = detect_test_framework(str(tmp_path))

        assert result.framework == "mocha"
        assert result.config_file == "package.json"
