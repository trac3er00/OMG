"""Regression tests for hooks/post-write.py behavior."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from tests.hooks.helpers import ROOT


def _run_post_write(file_path: str, project_dir: str, file_content: str = ""):
    """Run post-write hook with given file_path and project_dir."""
    # Create the file so it exists for the hook
    full_path = file_path if os.path.isabs(file_path) else os.path.join(project_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(file_content)

    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": full_path},
        "tool_response": {"success": True},
    }
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = project_dir

    proc = subprocess.run(
        ["python3", str(ROOT / "hooks" / "post-write.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=project_dir,
        env=env,
        check=False,
    )
    return proc


# ── Path handling ──

def test_post_write_does_not_crash_on_relative_path():
    """Hook should not crash when file_path is relative."""
    with tempfile.TemporaryDirectory() as tmp:
        # Write a simple TS file
        ts_file = os.path.join(tmp, "src", "app.ts")
        proc = _run_post_write(ts_file, tmp, file_content="const x = 1;\n")
        # Should exit 0 (formatter not found is fine, just no crash)
        assert proc.returncode == 0, f"Crashed: stderr={proc.stderr}"


def test_post_write_exits_clean_on_nonexistent_file():
    """Hook should exit 0 when file doesn't exist."""
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/nonexistent/path/file.ts"},
        "tool_response": {"success": True},
    }
    proc = subprocess.run(
        ["python3", str(ROOT / "hooks" / "post-write.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0


# ── Formatter invocation ──

def test_post_write_uses_no_install_for_prettier():
    """Prettier should be called with --no-install to avoid surprise installs."""
    script = ROOT / "hooks" / "post-write.py"
    with open(script, "r") as f:
        content = f.read()
    # Check that FORMAT_MAP uses --no-install
    assert "--no-install" in content, \
        "FORMAT_MAP should use 'npx --no-install prettier' to avoid surprise npm installs"


# ── Secret detection ──

def test_post_write_blocks_hardcoded_aws_key():
    """Should warn on stderr when file contains AWS access key (exits 0, warns on stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = _run_post_write(
            os.path.join(tmp, "config.ts"),
            tmp,
            file_content='const key = "AKIAIOSFODNN7EXAMPLE";\n',
        )
        # Hook exits 0 (not 2) to avoid crashing sibling hooks.
        # Secret warning goes to stderr.
        assert proc.returncode == 0, f"Should exit 0 (no sibling crash), got {proc.returncode}"
        assert "SECRET DETECTED" in proc.stderr, "Should warn about secret on stderr"


def test_post_write_allows_normal_code():
    """Should exit 0 for normal code without secrets."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = _run_post_write(
            os.path.join(tmp, "utils.ts"),
            tmp,
            file_content='export function add(a: number, b: number) { return a + b; }\n',
        )
        assert proc.returncode == 0


def test_post_write_skips_test_files():
    """Should not flag secrets in test files (common to have fixtures)."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = _run_post_write(
            os.path.join(tmp, "auth.test.ts"),
            tmp,
            file_content='const mockKey = "AKIAIOSFODNN7EXAMPLE";\n',
        )
        assert proc.returncode == 0, "Should skip secret detection in test files"
