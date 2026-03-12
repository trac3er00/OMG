#!/usr/bin/env python3
"""Unit tests for hooks/_common.py — verify _omg namespace (not _oal) for feature flags."""
import json
import os
import sys
import tempfile
from pathlib import Path

# Add hooks to path
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import get_feature_flag


def test_get_feature_flag_reads_from_omg_namespace():
    """Test that get_feature_flag reads from _omg namespace (not _oal)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        
        # Create settings.json with _omg namespace
        settings = {
            "_omg": {
                "features": {
                    "COST_TRACKING": True,
                    "MEMORY": False,
                    "PLANNING_ENFORCEMENT": True
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)
        
        # Clear cache and env vars to force settings.json read
        import _common
        _common._FEATURE_CACHE.clear()
        if "OMG_COST_TRACKING_ENABLED" in os.environ:
            del os.environ["OMG_COST_TRACKING_ENABLED"]
        if "OMG_MEMORY_ENABLED" in os.environ:
            del os.environ["OMG_MEMORY_ENABLED"]
        if "OMG_PLANNING_ENFORCEMENT_ENABLED" in os.environ:
            del os.environ["OMG_PLANNING_ENFORCEMENT_ENABLED"]
        
        # Test: get_feature_flag should read from _omg.features
        assert get_feature_flag("COST_TRACKING") == True, "Should read COST_TRACKING=True from _omg.features"
        assert get_feature_flag("MEMORY") == False, "Should read MEMORY=False from _omg.features"
        assert get_feature_flag("PLANNING_ENFORCEMENT") == True, "Should read PLANNING_ENFORCEMENT=True from _omg.features"


def test_get_feature_flag_ignores_oal_namespace():
    """Test that get_feature_flag does NOT read from legacy _oal namespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        
        # Create settings.json with ONLY _oal namespace (legacy, should be ignored)
        settings = {
            "_oal": {
                "features": {
                    "COST_TRACKING": True,
                    "MEMORY": True
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)
        
        # Clear cache and env vars
        import _common
        _common._FEATURE_CACHE.clear()
        if "OMG_COST_TRACKING_ENABLED" in os.environ:
            del os.environ["OMG_COST_TRACKING_ENABLED"]
        if "OMG_MEMORY_ENABLED" in os.environ:
            del os.environ["OMG_MEMORY_ENABLED"]
        
        # Test: get_feature_flag should NOT read from _oal, should return default
        assert get_feature_flag("COST_TRACKING", default=False) == False, "Should NOT read from _oal namespace, should return default"
        assert get_feature_flag("MEMORY", default=False) == False, "Should NOT read from _oal namespace, should return default"


def test_get_feature_flag_omg_takes_precedence():
    """Test that _omg namespace is used when both _oal and _omg exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        
        # Create settings.json with BOTH namespaces (should use _omg)
        settings = {
            "_oal": {
                "features": {
                    "COST_TRACKING": False,
                    "MEMORY": False
                }
            },
            "_omg": {
                "features": {
                    "COST_TRACKING": True,
                    "MEMORY": True
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)
        
        # Clear cache and env vars
        import _common
        _common._FEATURE_CACHE.clear()
        if "OMG_COST_TRACKING_ENABLED" in os.environ:
            del os.environ["OMG_COST_TRACKING_ENABLED"]
        if "OMG_MEMORY_ENABLED" in os.environ:
            del os.environ["OMG_MEMORY_ENABLED"]
        
        # Test: _omg values should be used, not _oal values
        assert get_feature_flag("COST_TRACKING") == True, "Should read from _omg (True), not _oal (False)"
        assert get_feature_flag("MEMORY") == True, "Should read from _omg (True), not _oal (False)"


def test_get_feature_flag_env_var_overrides_omg():
    """Test that env vars still override _omg namespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        os.environ["OMG_COST_TRACKING_ENABLED"] = "0"
        
        # Create settings.json with _omg namespace
        settings = {
            "_omg": {
                "features": {
                    "COST_TRACKING": True
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)
        
        # Clear cache
        import _common
        _common._FEATURE_CACHE.clear()
        
        # Test: env var should override _omg setting
        assert get_feature_flag("COST_TRACKING") == False, "Env var should override _omg namespace"
        
        # Cleanup
        del os.environ["OMG_COST_TRACKING_ENABLED"]


def test_bootstrap_runtime_paths_adds_active_project_dir():
    """Installed hooks should import repo-local runtime packages via CLAUDE_PROJECT_DIR."""
    import _common

    with tempfile.TemporaryDirectory() as tmpdir:
        hook_anchor = Path(tmpdir) / ".claude" / "hooks" / "firewall.py"
        hook_anchor.parent.mkdir(parents=True, exist_ok=True)
        project_dir = Path(tmpdir) / "workspace"
        project_dir.mkdir()

        old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        original_sys_path = list(sys.path)
        try:
            os.environ["CLAUDE_PROJECT_DIR"] = str(project_dir)
            while str(project_dir) in sys.path:
                sys.path.remove(str(project_dir))

            _common.bootstrap_runtime_paths(str(hook_anchor))

            resolved_sys_path = {str(Path(path).resolve()) for path in sys.path}
            assert str(project_dir.resolve()) in resolved_sys_path
        finally:
            sys.path[:] = original_sys_path
            if old_project_dir is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
            else:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)


if __name__ == "__main__":
    # Run tests manually if pytest not available
    test_get_feature_flag_reads_from_omg_namespace()
    print("✓ test_get_feature_flag_reads_from_omg_namespace passed")
    
    test_get_feature_flag_ignores_oal_namespace()
    print("✓ test_get_feature_flag_ignores_oal_namespace passed")
    
    test_get_feature_flag_omg_takes_precedence()
    print("✓ test_get_feature_flag_omg_takes_precedence passed")
    
    test_get_feature_flag_env_var_overrides_omg()
    print("✓ test_get_feature_flag_env_var_overrides_omg passed")
    
    print("\nAll tests passed!")
