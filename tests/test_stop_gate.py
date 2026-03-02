#!/usr/bin/env python3
"""Unit tests for hooks/stop-gate.py"""
import subprocess
import json
import sys
import os


def test_stop_hook_active_guard():
    """Test that stop_hook_active=true causes immediate exit(0) with no output."""
    # Prepare input: stop_hook_active=true
    input_data = json.dumps({"stop_hook_active": True})
    
    # Run stop-gate.py with the input
    result = subprocess.run(
        [sys.executable, "hooks/stop-gate.py"],
        input=input_data.encode(),
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    
    # Verify: exit code 0
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"
    
    # Verify: no stdout output
    assert result.stdout == b"", f"Expected empty stdout, got: {result.stdout}"
    
    # Verify: no stderr output
    assert result.stderr == b"", f"Expected empty stderr, got: {result.stderr}"


def test_stop_hook_active_false_normal_flow():
    """Test that stop_hook_active=false allows normal flow (exits 0 with no blocks)."""
    # Prepare input: stop_hook_active=false
    input_data = json.dumps({"stop_hook_active": False})
    
    # Run stop-gate.py with the input
    result = subprocess.run(
        [sys.executable, "hooks/stop-gate.py"],
        input=input_data.encode(),
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    
    # Verify: exit code 0
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"


def test_stop_hook_active_missing_defaults_to_false():
    """Test that missing stop_hook_active key defaults to false (normal flow)."""
    # Prepare input: no stop_hook_active key
    input_data = json.dumps({})
    
    # Run stop-gate.py with the input
    result = subprocess.run(
        [sys.executable, "hooks/stop-gate.py"],
        input=input_data.encode(),
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    
    # Verify: exit code 0
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"



def test_stop_gate_invalid_json_exits_zero():
    """Invalid JSON input must exit 0 — crash isolation invariant."""
    result = subprocess.run(
        [sys.executable, "hooks/stop-gate.py"],
        input=b"not valid json {{{{",
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    assert result.returncode == 0, f"Expected exit 0 on invalid JSON, got {result.returncode}"


def test_stop_gate_no_crash_without_git(tmp_path):
    """stop-gate should exit 0 even when not in a git repo (CHECK 2 skip)."""
    (tmp_path / '.oal' / 'state' / 'ledger').mkdir(parents=True)
    input_data = json.dumps({})
    result = subprocess.run(
        [sys.executable, "hooks/stop-gate.py"],
        input=input_data.encode(),
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, 'CLAUDE_PROJECT_DIR': str(tmp_path)}
    )
    assert result.returncode == 0


if __name__ == "__main__":
    test_stop_hook_active_guard()
    test_stop_hook_active_false_normal_flow()
    test_stop_hook_active_missing_defaults_to_false()
    test_stop_gate_invalid_json_exits_zero()
    print("All tests passed!")
