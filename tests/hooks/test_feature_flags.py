"""Tests for feature flag system in hooks/_common.py."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Add hooks to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hooks"))

import _common


def test_get_feature_flag_reads_from_omg_not_oal():
    """Feature flags should read from settings.json._omg.features, not _oal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create settings.json with _omg.features (correct key)
        settings_path = Path(tmpdir) / "settings.json"
        settings_path.write_text(
            json.dumps({
                "_omg": {
                    "features": {
                        "THEMES": True,
                        "INTENTGATE": False,
                    }
                }
            }),
            encoding="utf-8"
        )
        
        # Clear the cache before test
        _common._FEATURE_CACHE.clear()
        
        # Set project dir to temp directory
        old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        try:
            os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
            
            # Test: THEMES should be True (from _omg.features)
            result = _common.get_feature_flag("THEMES", default=False)
            assert result is True, f"Expected THEMES=True from _omg.features, got {result}"
            
            # Test: INTENTGATE should be False (from _omg.features)
            result = _common.get_feature_flag("INTENTGATE", default=True)
            assert result is False, f"Expected INTENTGATE=False from _omg.features, got {result}"
            
        finally:
            # Restore env and clear cache
            if old_project_dir is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
            else:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            _common._FEATURE_CACHE.clear()


def test_get_feature_flag_env_var_overrides_settings():
    """Environment variables should override settings.json values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create settings.json with THEMES=False
        settings_path = Path(tmpdir) / "settings.json"
        settings_path.write_text(
            json.dumps({
                "_omg": {
                    "features": {
                        "THEMES": False,
                    }
                }
            }),
            encoding="utf-8"
        )
        
        # Clear the cache before test
        _common._FEATURE_CACHE.clear()
        
        # Set project dir and env var
        old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        old_env_var = os.environ.get("OMG_THEMES_ENABLED")
        try:
            os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
            os.environ["OMG_THEMES_ENABLED"] = "1"
            
            # Test: env var should override settings.json
            result = _common.get_feature_flag("THEMES", default=False)
            assert result is True, f"Expected env var to override settings.json, got {result}"
            
        finally:
            # Restore env and clear cache
            if old_project_dir is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
            else:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            if old_env_var is not None:
                os.environ["OMG_THEMES_ENABLED"] = old_env_var
            else:
                os.environ.pop("OMG_THEMES_ENABLED", None)
            _common._FEATURE_CACHE.clear()


def test_get_feature_flag_returns_default_when_missing():
    """Should return default value when flag is not in settings.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create settings.json with no NONEXISTENT flag
        settings_path = Path(tmpdir) / "settings.json"
        settings_path.write_text(
            json.dumps({
                "_omg": {
                    "features": {
                        "THEMES": True,
                    }
                }
            }),
            encoding="utf-8"
        )
        
        # Clear the cache before test
        _common._FEATURE_CACHE.clear()
        
        # Set project dir
        old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        try:
            os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
            
            # Test: missing flag should return default
            result = _common.get_feature_flag("NONEXISTENT", default=True)
            assert result is True, f"Expected default=True for missing flag, got {result}"
            
        finally:
            # Restore env and clear cache
            if old_project_dir is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
            else:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            _common._FEATURE_CACHE.clear()


def test_get_feature_flag_all_11_flags_exist():
    """All 11 feature flags should be readable from settings.json._omg.features."""
    expected_flags = [
        "THEMES",
        "INTENTGATE",
        "MULTI_CREDENTIAL",
        "MODEL_ROLES",
        "LSP",
        "HASHLINE",
        "PYTHON_REPL",
        "WEB_SEARCH",
        "BROWSER",
        "SSH",
        "RUST_ENGINE",
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create settings.json with all flags
        features = {flag: True for flag in expected_flags}
        settings_path = Path(tmpdir) / "settings.json"
        settings_path.write_text(
            json.dumps({
                "_omg": {
                    "features": features
                }
            }),
            encoding="utf-8"
        )
        
        # Clear the cache before test
        _common._FEATURE_CACHE.clear()
        
        # Set project dir
        old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        try:
            os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
            
            # Test: all flags should be readable
            for flag in expected_flags:
                result = _common.get_feature_flag(flag, default=False)
                assert result is True, f"Expected {flag}=True, got {result}"
            
        finally:
            # Restore env and clear cache
            if old_project_dir is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
            else:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            _common._FEATURE_CACHE.clear()
