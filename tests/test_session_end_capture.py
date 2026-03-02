#!/usr/bin/env python3
"""Unit tests for hooks/session-end-capture.py."""
import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Add hooks to path
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)


def test_exits_zero_with_valid_input():
    """Test that session-end-capture exits 0 with valid session_id."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")
    
    # Valid input with session_id
    input_data = json.dumps({"session_id": "test-session-123", "cwd": "/tmp"})
    
    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"


def test_exits_zero_with_invalid_json():
    """Test that session-end-capture exits 0 with invalid JSON (crash isolation)."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")
    
    # Invalid JSON input
    input_data = "{ invalid json }"
    
    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Expected exit 0 on invalid JSON, got {result.returncode}. stderr: {result.stderr}"


def test_exits_zero_with_missing_session_id():
    """Test that session-end-capture exits 0 even with missing session_id."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")
    
    # Valid JSON but no session_id
    input_data = json.dumps({"cwd": "/tmp"})
    
    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Expected exit 0 with missing session_id, got {result.returncode}"


def test_exits_zero_with_empty_input():
    """Test that session-end-capture exits 0 with empty input."""
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")
    
    # Empty input
    input_data = ""
    
    result = subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Expected exit 0 with empty input, got {result.returncode}"
