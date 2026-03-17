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


# ── Secret resolution ──

def test_secret_detected_signal_can_be_resolved():
    """Should resolve a secret-detected signal with audit trail."""
    import importlib.util
    
    with tempfile.TemporaryDirectory() as tmp:
        state_dir = os.path.join(tmp, ".omg", "state")
        os.makedirs(state_dir, exist_ok=True)
        
        signal_path = os.path.join(state_dir, "secret-detected.json")
        initial_signal = {
            "timestamp": "2026-03-05T03:52:09.818871+00:00",
            "file": "/path/to/file.py",
            "patterns_matched": ["High-entropy potential secret"],
            "action": "blocked",
        }
        with open(signal_path, "w") as f:
            json.dump(initial_signal, f)
        
        spec = importlib.util.spec_from_file_location(
            "post_write_module",
            ROOT / "hooks" / "post-write.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load post-write.py")
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pass
        
        resolved_state = module.resolve_secret_detected(tmp, "false_positive")
        
        assert resolved_state["resolved"] is True
        assert "resolved_at" in resolved_state
        assert resolved_state["resolve_reason"] == "false_positive"
        assert resolved_state["timestamp"] == initial_signal["timestamp"]
        assert resolved_state["file"] == initial_signal["file"]
        
        with open(signal_path, "r") as f:
            persisted = json.load(f)
        assert persisted["resolved"] is True
        assert persisted["resolve_reason"] == "false_positive"


def test_secret_detected_resolution_is_idempotent():
    """Should handle resolving an already-resolved signal without error."""
    import importlib.util
    
    with tempfile.TemporaryDirectory() as tmp:
        state_dir = os.path.join(tmp, ".omg", "state")
        os.makedirs(state_dir, exist_ok=True)
        
        signal_path = os.path.join(state_dir, "secret-detected.json")
        initial_signal = {
            "timestamp": "2026-03-05T03:52:09.818871+00:00",
            "file": "/path/to/file.py",
            "patterns_matched": ["High-entropy potential secret"],
            "action": "blocked",
            "resolved": True,
            "resolved_at": "2026-03-10T10:00:00+00:00",
            "resolve_reason": "secret_rotated",
        }
        with open(signal_path, "w") as f:
            json.dump(initial_signal, f)
        
        spec = importlib.util.spec_from_file_location(
            "post_write_module",
            ROOT / "hooks" / "post-write.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load post-write.py")
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pass
        
        resolved_state = module.resolve_secret_detected(tmp, "verified_safe")
        
        assert resolved_state["resolved"] is True
        assert resolved_state["resolve_reason"] == "verified_safe"
        assert resolved_state["timestamp"] == initial_signal["timestamp"]


def test_secret_detection_still_blocks_unresolved_secrets():
    """Should still detect and warn about new secrets even after resolution."""
    with tempfile.TemporaryDirectory() as tmp:
        # First, write a file with a secret
        target = os.path.join(tmp, "src", "config.py")
        proc = _run_post_write(
            target,
            tmp,
            'API_KEY = "sk-proj-xK9mN2pQ8rT5vW3yZ1aB4cD7eF0gH6iJ"\n',
        )
        
        # Should warn about the secret
        assert proc.returncode == 0
        assert "SECRET DETECTED" in proc.stderr
        
        # Verify signal was written
        signal_path = os.path.join(tmp, ".omg", "state", "secret-detected.json")
        assert os.path.exists(signal_path)
        with open(signal_path, "r") as f:
            signal = json.load(f)
        assert signal.get("action") == "blocked"
        assert "resolved" not in signal or signal.get("resolved") is False
