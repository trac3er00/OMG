#!/usr/bin/env python3
"""Unit tests for hooks/_common.py utilities."""
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add hooks to path
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import log_hook_error, atomic_json_write, get_feature_flag


def test_log_hook_error():
    """Test log_hook_error writes to hook-errors.jsonl with correct format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set project dir to temp directory
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        
        # Call log_hook_error
        log_hook_error("test-hook", ValueError("test error"), context={"key": "value"})
        
        # Verify file was created
        ledger_path = os.path.join(tmpdir, ".omg", "state", "ledger", "hook-errors.jsonl")
        assert os.path.exists(ledger_path), f"hook-errors.jsonl not created at {ledger_path}"
        
        # Verify content
        with open(ledger_path, "r") as f:
            line = f.read().strip()
        
        entry = json.loads(line)
        assert entry["hook"] == "test-hook"
        assert entry["error"] == "test error"
        assert entry["context"] == {"key": "value"}
        assert "ts" in entry
        assert "T" in entry["ts"] or "+" in entry["ts"]


def test_log_hook_error_rotation():
    """Test log_hook_error rotates file when > 100KB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        
        ledger_path = os.path.join(tmpdir, ".omg", "state", "ledger", "hook-errors.jsonl")
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        
        # Create a file > 100KB
        with open(ledger_path, "w") as f:
            f.write("x" * (101 * 1024))
        
        # Call log_hook_error
        log_hook_error("test-hook", RuntimeError("error"))
        
        # Verify rotation happened
        archive_path = ledger_path + ".1"
        assert os.path.exists(archive_path), "Archive file not created"
        assert os.path.getsize(ledger_path) < 101 * 1024, "New file should be smaller"


def test_atomic_json_write():
    """Test atomic_json_write creates file with correct JSON content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = os.path.join(tmpdir, "subdir", "test.json")
        data = {"key": "value", "number": 42}
        
        # Call atomic_json_write
        atomic_json_write(target_path, data)
        
        # Verify file exists
        assert os.path.exists(target_path), f"File not created at {target_path}"
        
        # Verify content
        with open(target_path, "r") as f:
            content = json.load(f)
        
        assert content == data, f"Content mismatch: {content} != {data}"


def test_atomic_json_write_no_tmp_leftover():
    """Test atomic_json_write cleans up temp file on success."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = os.path.join(tmpdir, "test.json")
        data = {"test": "data"}
        
        atomic_json_write(target_path, data)
        
        # Verify no .tmp file left behind
        tmp_path = target_path + ".tmp"
        assert not os.path.exists(tmp_path), f"Temp file not cleaned up: {tmp_path}"


def test_atomic_json_write_silent_failure():
    """Test atomic_json_write silently fails on error."""
    # Try to write to a path that can't be created (permission denied)
    # This should not raise an exception
    try:
        atomic_json_write("/root/cannot-write-here.json", {"test": "data"})
        # If we get here, the function silently failed as expected
        assert True
    except Exception as e:
        assert False, f"atomic_json_write should not raise: {e}"


def test_feature_flags():
    """Test feature flag resolution order: env var -> settings.json -> default."""
    # Test 1: env var false values
    os.environ["OMG_MEMORY_ENABLED"] = "0"
    import _common
    _common._FEATURE_CACHE.clear()
    assert not get_feature_flag("memory"), "Env var '0' should return False"
    
    os.environ["OMG_MEMORY_ENABLED"] = "false"
    _common._FEATURE_CACHE.clear()
    assert not get_feature_flag("memory"), "Env var 'false' should return False"
    
    os.environ["OMG_MEMORY_ENABLED"] = "no"
    _common._FEATURE_CACHE.clear()
    assert not get_feature_flag("memory"), "Env var 'no' should return False"
    
    # Test 2: env var true values
    os.environ["OMG_MEMORY_ENABLED"] = "1"
    _common._FEATURE_CACHE.clear()
    assert get_feature_flag("memory"), "Env var '1' should return True"
    
    os.environ["OMG_MEMORY_ENABLED"] = "true"
    _common._FEATURE_CACHE.clear()
    assert get_feature_flag("memory"), "Env var 'true' should return True"
    
    os.environ["OMG_MEMORY_ENABLED"] = "yes"
    _common._FEATURE_CACHE.clear()
    assert get_feature_flag("memory"), "Env var 'yes' should return True"
    
    # Test 3: default value when no env var
    if "OMG_MEMORY_ENABLED" in os.environ:
        del os.environ["OMG_MEMORY_ENABLED"]
    _common._FEATURE_CACHE.clear()
    assert get_feature_flag("unknown_flag") == True, "Default should be True"
    assert get_feature_flag("unknown_flag", default=False) == False, "Custom default should work"
    
    # Test 4: settings.json reading
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        settings = {
            "_omg": {
                "features": {
                    "memory": True,
                    "ralph_loop": False,
                    "planning_enforcement": True
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)
        
        _common._FEATURE_CACHE.clear()
        assert get_feature_flag("memory") == True, "Should read memory=True from settings.json"
        assert get_feature_flag("ralph_loop") == False, "Should read ralph_loop=False from settings.json"
        assert get_feature_flag("planning_enforcement") == True, "Should read planning_enforcement=True from settings.json"
    
    # Test 5: env var overrides settings.json
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        os.environ["OMG_MEMORY_ENABLED"] = "0"
        settings = {"_omg": {"features": {"memory": True}}}
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)
        
        _common._FEATURE_CACHE.clear()
        assert not get_feature_flag("memory"), "Env var should override settings.json"
    
    # Test 6: malformed settings.json
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        if "OMG_MEMORY_ENABLED" in os.environ:
            del os.environ["OMG_MEMORY_ENABLED"]
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            f.write("{ invalid json }")
        
        _common._FEATURE_CACHE.clear()
        assert get_feature_flag("memory") == True, "Should return default on malformed JSON"
    
    # Test 7: missing features section
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        if "OMG_MEMORY_ENABLED" in os.environ:
            del os.environ["OMG_MEMORY_ENABLED"]
        settings = {"_omg": {}}
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)
        
        _common._FEATURE_CACHE.clear()
        assert get_feature_flag("memory") == True, "Should return default when features section missing"

if __name__ == "__main__":
    # Run tests manually if pytest not available
    test_log_hook_error()
    print("✓ test_log_hook_error passed")
    
    test_log_hook_error_rotation()
    print("✓ test_log_hook_error_rotation passed")
    
    test_atomic_json_write()
    print("✓ test_atomic_json_write passed")
    
    test_atomic_json_write_no_tmp_leftover()
    print("✓ test_atomic_json_write_no_tmp_leftover passed")
    
    test_atomic_json_write_silent_failure()
    print("✓ test_atomic_json_write_silent_failure passed")
    
    test_feature_flags()
    print("✓ test_feature_flags passed")
    
    print("\nAll tests passed!")


