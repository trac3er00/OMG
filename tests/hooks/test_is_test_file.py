"""Tests for _is_test_file() heuristic in hooks/test-validator.py.

Verifies that source modules (e.g. runtime/test_intent_lock.py) and build
artifacts are correctly excluded, while genuine test files are accepted.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Import test-validator.py via importlib (hyphenated filename)
_HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

_spec = importlib.util.spec_from_file_location(
    "test_validator", str(_HOOKS_DIR / "test-validator.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_is_test_file = _mod._is_test_file


# --- True positives: genuine test files ---

@pytest.mark.parametrize(
    "path",
    [
        pytest.param("tests/test_auth.py", id="tests-dir-test-prefix"),
        pytest.param("test/test_utils.py", id="test-dir-test-prefix"),
        pytest.param("tests/hooks/test_validator_v2.py", id="nested-tests-dir"),
        pytest.param("src/components/Button.test.tsx", id="dot-test-tsx"),
        pytest.param("src/utils.spec.js", id="dot-spec-js"),
        pytest.param("lib/parser_test.py", id="underscore-test-suffix"),
        pytest.param("__tests__/App.test.js", id="dunder-tests-dir"),
        pytest.param("src/__tests__/helpers.test.ts", id="nested-dunder-tests"),
        pytest.param("test_standalone.py", id="repo-root-test-prefix"),
        pytest.param("tests/integration/test_api.py", id="deep-tests-dir"),
        pytest.param("app.tests.js", id="dot-tests-js"),
    ],
)
def test_genuine_test_files_accepted(path):
    """Genuine test files should be recognized as test files."""
    assert _is_test_file(path) is True, f"Expected True for {path}"


# --- True negatives: source modules and non-test files ---

@pytest.mark.parametrize(
    "path",
    [
        pytest.param("runtime/test_intent_lock.py", id="source-module-test-prefix"),
        pytest.param("hooks/test-validator.py", id="source-hook-test-prefix"),
        pytest.param("runtime/api_twin.py", id="plain-source-module"),
        pytest.param("src/utils.py", id="no-test-pattern"),
        pytest.param("lib/helpers.py", id="lib-module"),
        pytest.param("runtime/adapters/claude.py", id="nested-source"),
    ],
)
def test_source_modules_excluded(path):
    """Source modules that happen to have 'test' in the name should NOT match."""
    assert _is_test_file(path) is False, f"Expected False for {path}"


# --- Build artifacts always excluded ---

@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            "build/lib/runtime/test_intent_lock.py",
            id="build-lib-source",
        ),
        pytest.param(
            "build/bdist.macosx-26.2-arm64/wheel/runtime/test_intent_lock.py",
            id="build-wheel-source",
        ),
        pytest.param(
            "build/lib/hooks/test-validator.py",
            id="build-lib-hook",
        ),
        pytest.param(
            "dist/test_something.py",
            id="dist-dir",
        ),
        pytest.param(
            "node_modules/pkg/test_utils.py",
            id="node-modules",
        ),
        pytest.param(
            ".git/hooks/test_pre_commit.py",
            id="dot-git-dir",
        ),
        pytest.param(
            "build/lib/tests/test_auth.py",
            id="build-genuine-test-still-excluded",
        ),
    ],
)
def test_build_artifacts_excluded(path):
    """Files under build/, dist/, node_modules/, .git/ should always be excluded."""
    assert _is_test_file(path) is False, f"Expected False for {path}"


# --- Edge cases ---

def test_windows_backslash_paths():
    """Backslash paths (Windows-style) should be normalized correctly."""
    assert _is_test_file("tests\\test_auth.py") is True
    assert _is_test_file("build\\lib\\test_auth.py") is False
    assert _is_test_file("runtime\\test_intent_lock.py") is False


def test_empty_and_degenerate_inputs():
    """Edge cases that shouldn't crash."""
    assert _is_test_file("") is False
    assert _is_test_file("test_") is True  # at root with test_ prefix → accepted
    assert _is_test_file("/") is False
