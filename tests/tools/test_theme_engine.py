import json
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from tools.theme_engine import Theme, ThemeEngine, is_themes_enabled


@pytest.fixture
def enable_themes():
    with patch.dict(os.environ, {"OMG_THEMES_ENABLED": "true"}):
        yield


class TestTheme:
    def test_dataclass_fields(self):
        """Test Theme dataclass fields."""
        theme = Theme(
            name="test-theme",
            variant="dark",
            colors={"background": "#000000", "foreground": "#ffffff"},
            metadata={"author": "test"}
        )
        assert theme.name == "test-theme"
        assert theme.variant == "dark"
        assert theme.colors["background"] == "#000000"
        assert theme.metadata["author"] == "test"

    def test_from_dict(self):
        """Test creating Theme from dictionary."""
        data = {
            "name": "dict-theme",
            "variant": "light",
            "colors": {"primary": "#ff0000"},
            "metadata": {"version": "1.0"}
        }
        theme = Theme.from_dict(data)
        assert theme.name == "dict-theme"
        assert theme.variant == "light"
        assert theme.colors["primary"] == "#ff0000"
        assert theme.metadata["version"] == "1.0"


class TestDetectCapabilities:
    def test_truecolor_detection(self, enable_themes):
        """Test truecolor detection."""
        engine = ThemeEngine()
        with patch.dict(os.environ, {"COLORTERM": "truecolor", "TERM": "xterm"}):
            caps = engine.detect_capabilities()
            assert caps["truecolor"] is True
            assert caps["256color"] is True
            assert caps["basic"] is True

    def test_256color_detection(self, enable_themes):
        """Test 256color detection."""
        engine = ThemeEngine()
        with patch.dict(os.environ, {"COLORTERM": "", "TERM": "xterm-256color"}):
            caps = engine.detect_capabilities()
            assert caps["truecolor"] is False
            assert caps["256color"] is True
            assert caps["basic"] is True

    def test_dark_mode_detection(self, enable_themes):
        """Test dark mode detection."""
        engine = ThemeEngine()
        # Dark mode (bg < 8)
        with patch.dict(os.environ, {"COLORFGBG": "15;0"}):
            caps = engine.detect_capabilities()
            assert caps["dark_mode"] is True
            
        # Light mode (bg >= 8)
        with patch.dict(os.environ, {"COLORFGBG": "0;15"}):
            caps = engine.detect_capabilities()
            assert caps["dark_mode"] is False


class TestLoadTheme:
    def test_loads_yaml(self, enable_themes):
        """Test loading theme from YAML."""
        engine = ThemeEngine()
        yaml_content = """
name: test-theme
variant: dark
colors:
  background: "#000000"
"""
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                theme = engine.load_theme("test-theme")
                assert theme is not None
                assert theme.name == "test-theme"
                assert theme.colors["background"] == "#000000"

    def test_handles_missing_theme(self, enable_themes):
        """Test handling missing theme."""
        engine = ThemeEngine()
        with patch("os.path.exists", return_value=False):
            theme = engine.load_theme("missing-theme")
            assert theme is None


class TestApplyTheme:
    def test_returns_ansi_codes(self, enable_themes):
        """Test returning ANSI escape codes."""
        engine = ThemeEngine()
        theme = Theme(
            name="test",
            variant="dark",
            colors={"primary": "#ff0000"}
        )
        
        with patch.object(engine, "detect_capabilities", return_value={"truecolor": True, "256color": True, "basic": True, "dark_mode": True}):
            codes = engine.apply_theme(theme)
            assert "primary" in codes
            assert codes["primary"] == "\033[38;2;255;0;0m"
            
        with patch.object(engine, "detect_capabilities", return_value={"truecolor": False, "256color": True, "basic": True, "dark_mode": True}):
            codes = engine.apply_theme(theme)
            assert "primary" in codes
            assert codes["primary"] == "\033[38;5;196m"

    def test_handles_no_capabilities(self, enable_themes):
        """Test handling no terminal capabilities."""
        engine = ThemeEngine()
        theme = Theme(
            name="test",
            variant="dark",
            colors={"primary": "#ff0000"}
        )
        
        with patch.object(engine, "detect_capabilities", return_value={"truecolor": False, "256color": False, "basic": False, "dark_mode": True}):
            codes = engine.apply_theme(theme)
            assert codes == {}


class TestPreference:
    def test_save_preference_writes(self, enable_themes):
        """Test save_preference writes to file."""
        engine = ThemeEngine()
        
        # Mock _atomic_json_write
        mock_write = MagicMock()
        with patch("tools.theme_engine._atomic_json_write", mock_write):
            result = engine.save_preference("my-theme")
            assert result is True
            mock_write.assert_called_once()
            args, _ = mock_write.call_args
            assert args[0] == engine.state_file
            assert args[1]["theme"] == "my-theme"
            assert "set_at" in args[1]

    def test_get_preference_reads(self, enable_themes):
        """Test get_preference reads from file."""
        engine = ThemeEngine()
        
        json_content = '{"theme": "my-theme", "set_at": "2023-01-01T00:00:00Z"}'
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json_content)):
                pref = engine.get_preference()
                assert pref == "my-theme"


class TestGetAvailableThemes:
    def test_lists_themes(self, enable_themes):
        """Test listing available themes."""
        engine = ThemeEngine()
        
        with patch("os.path.exists", return_value=True):
            with patch("os.listdir", return_value=["theme1.yaml", "theme2.yml", "not-a-theme.txt"]):
                themes = engine.get_available_themes()
                assert len(themes) == 2
                assert "theme1" in themes
                assert "theme2" in themes

    def test_empty_dir_returns_empty_list(self, enable_themes):
        """Test empty directory returns empty list."""
        engine = ThemeEngine()
        
        with patch("os.path.exists", return_value=True):
            with patch("os.listdir", return_value=[]):
                themes = engine.get_available_themes()
                assert themes == []
