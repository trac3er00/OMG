"""Tests for PostToolUse test generation integration hook (T33)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "hooks"
SCRIPT_PATH = HOOKS_DIR / "test_generator_hook.py"


def _run_hook(
    payload: dict[str, Any],
    project_dir: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    full_env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    # Ensure feature flag is NOT set via env unless caller overrides
    full_env.pop("OMG_TEST_GENERATION_ENABLED", None)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(project_dir),
        env=full_env,
        check=False,
    )
    return proc


def _make_payload(
    tool_name: str = "Write",
    file_path: str = "src/utils.py",
    tool_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
        "tool_response": tool_response or {"success": True},
        "session_id": "test-session-123",
    }


def _write_settings(project_dir: Path, features: dict[str, Any] | None = None) -> None:
    data = {"_omg": {"features": features or {"TEST_GENERATION": True}}}
    (project_dir / "settings.json").write_text(json.dumps(data), encoding="utf-8")


# ── Test 1: Source file Write triggers suggestion ──


def test_source_file_triggers_suggestion():
    """Write to a source file with no corresponding test → additionalContext injected."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": True})
        # Create source file but NO test file
        src = project_dir / "src"
        src.mkdir()
        (src / "utils.py").write_text("def add(a, b): return a + b\n")

        proc = _run_hook(_make_payload("Write", "src/utils.py"), project_dir)

        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert "additionalContext" in output
        assert "src/utils.py" in output["additionalContext"]
        assert "testgen" in output["additionalContext"].lower() or "test" in output["additionalContext"].lower()


# ── Test 2: Test file does NOT trigger ──


def test_test_file_no_trigger():
    """Write to a test file → no output (silent exit 0)."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": True})

        proc = _run_hook(_make_payload("Write", "tests/test_utils.py"), project_dir)

        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


# ── Test 3: Non-write tool does NOT trigger ──


def test_non_write_tool_no_trigger():
    """Bash tool → no output (silent exit 0)."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": True})

        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"stdout": "file.txt"},
            "session_id": "test-session-123",
        }
        proc = _run_hook(payload, project_dir)

        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


# ── Test 4: Feature flag disabled → silent exit ──


def test_feature_flag_disabled_no_output():
    """TEST_GENERATION flag off → silent exit 0, no output."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": False})

        proc = _run_hook(_make_payload("Write", "src/utils.py"), project_dir)

        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


# ── Test 5: Existing test file → no suggestion ──


def test_existing_test_file_no_suggestion():
    """Source file modified but corresponding test file exists → no suggestion."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": True})
        # Create source file AND corresponding test file
        src = project_dir / "src"
        src.mkdir()
        (src / "utils.py").write_text("def add(a, b): return a + b\n")
        tests = project_dir / "tests"
        tests.mkdir()
        (tests / "test_utils.py").write_text("def test_add(): pass\n")

        proc = _run_hook(_make_payload("Write", "src/utils.py"), project_dir)

        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


# ── Test 6: Edit tool also triggers ──


def test_edit_tool_triggers_suggestion():
    """Edit tool on source file with no test → additionalContext injected."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": True})
        src = project_dir / "src"
        src.mkdir()
        (src / "handler.py").write_text("def handle(): pass\n")

        proc = _run_hook(_make_payload("Edit", "src/handler.py"), project_dir)

        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert "additionalContext" in output
        assert "handler.py" in output["additionalContext"]


# ── Test 7: Feature flag via env var overrides settings.json ──


def test_feature_flag_env_var_override():
    """Env var OMG_TEST_GENERATION_ENABLED=1 enables even when settings says false."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": False})
        src = project_dir / "src"
        src.mkdir()
        (src / "core.py").write_text("def run(): pass\n")

        proc = _run_hook(
            _make_payload("Write", "src/core.py"),
            project_dir,
            env={"OMG_TEST_GENERATION_ENABLED": "1"},
        )

        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert "additionalContext" in output


# ── Test 8: Various test file patterns are skipped ──


def test_various_test_file_patterns_skipped():
    """Files matching test patterns (spec, _test, /test/) → no output."""
    test_paths = [
        "src/utils.test.ts",
        "src/utils.spec.ts",
        "src/utils_test.py",
        "test/integration.py",
        "tests/conftest.py",
        "src/__tests__/foo.js",
    ]
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": True})

        for path in test_paths:
            proc = _run_hook(_make_payload("Write", path), project_dir)
            assert proc.returncode == 0, f"Non-zero exit for {path}"
            assert proc.stdout.strip() == "", f"Unexpected output for test file: {path}"


# ── Test 9: path field fallback ──


def test_path_field_fallback():
    """tool_input uses 'path' instead of 'file_path' → still works."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"TEST_GENERATION": True})
        src = project_dir / "lib"
        src.mkdir()
        (src / "parser.py").write_text("def parse(): pass\n")

        payload = {
            "tool_name": "Write",
            "tool_input": {"path": "lib/parser.py"},
            "tool_response": {"success": True},
            "session_id": "test-session-123",
        }
        proc = _run_hook(payload, project_dir)

        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert "additionalContext" in output
        assert "parser.py" in output["additionalContext"]
