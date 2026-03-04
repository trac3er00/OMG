import json
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest

from tools.theme_engine import Theme, ThemeEngine
from tools.theme_selector import ThemeSelector, is_themes_enabled

@pytest.fixture
def mock_theme_engine():
    engine = MagicMock(spec=ThemeEngine)
    
    # Mock get_available_themes
    engine.get_available_themes.return_value = ["catppuccin-mocha", "catppuccin-latte", "dracula"]
    
    # Mock load_theme
    def mock_load_theme(name):
        if name == "catppuccin-mocha":
            return Theme(
                name="catppuccin-mocha",
                variant="dark",
                colors={"background": "#1e1e2e", "foreground": "#cdd6f4"},
                metadata={}
            )
        elif name == "catppuccin-latte":
            return Theme(
                name="catppuccin-latte",
                variant="light",
                colors={"background": "#eff1f5", "foreground": "#4c4f69"},
                metadata={}
            )
        return None
    engine.load_theme.side_effect = mock_load_theme
    
    # Mock apply_theme
    engine.apply_theme.return_value = {
        "background": "\033[38;2;30;30;46m",
        "foreground": "\033[38;2;205;214;244m"
    }
    
    # Mock save_preference
    engine.save_preference.return_value = True
    
    # Mock get_preference
    engine.get_preference.return_value = "catppuccin-mocha"
    
    # Mock detect_capabilities
    engine.detect_capabilities.return_value = {"dark_mode": True, "basic": True, "truecolor": True}
    
    return engine

@pytest.fixture
def selector(mock_theme_engine):
    return ThemeSelector(engine=mock_theme_engine)

@pytest.fixture
def enable_themes():
    with patch("tools.theme_selector.is_themes_enabled", return_value=True):
        yield

@pytest.fixture
def disable_themes():
    with patch("tools.theme_selector.is_themes_enabled", return_value=False):
        yield

class TestThemeSelector:
    def test_list_themes_enabled(self, selector, enable_themes):
        """Test listing themes when enabled."""
        themes = selector.list_themes()
        assert isinstance(themes, list)
        assert themes == ["catppuccin-latte", "catppuccin-mocha", "dracula"]
        selector.engine.get_available_themes.assert_called_once()

    def test_list_themes_disabled(self, selector, disable_themes):
        """Test listing themes when disabled."""
        result = selector.list_themes()
        assert isinstance(result, dict)
        assert "error" in result
        assert result["error"] == "Themes are disabled"

    def test_preview_theme_enabled_valid(self, selector, enable_themes):
        """Test previewing a valid theme when enabled."""
        result = selector.preview_theme("catppuccin-mocha")
        assert "error" not in result
        assert result["name"] == "catppuccin-mocha"
        assert "background" in result["colors"]
        assert "ansi_preview" in result
        assert "Preview for catppuccin-mocha:" in result["ansi_preview"]
        assert "\033[38;2;30;30;46m" in result["ansi_preview"]
        
        selector.engine.load_theme.assert_called_once_with("catppuccin-mocha")
        selector.engine.apply_theme.assert_called_once()
        selector.engine.save_preference.assert_not_called()

    def test_preview_theme_enabled_invalid(self, selector, enable_themes):
        """Test previewing an invalid theme when enabled."""
        result = selector.preview_theme("invalid-theme")
        assert "error" in result
        assert result["error"] == "Theme 'invalid-theme' not found"

    def test_preview_theme_disabled(self, selector, disable_themes):
        """Test previewing a theme when disabled."""
        result = selector.preview_theme("catppuccin-mocha")
        assert "error" in result
        assert result["error"] == "Themes are disabled"

    def test_set_theme_enabled_valid(self, selector, enable_themes):
        """Test setting a valid theme when enabled."""
        result = selector.set_theme("catppuccin-mocha")
        assert "error" not in result
        assert result["success"] is True
        assert result["theme"] == "catppuccin-mocha"
        assert "applied_at" in result
        
        selector.engine.load_theme.assert_called_once_with("catppuccin-mocha")
        selector.engine.apply_theme.assert_called_once()
        selector.engine.save_preference.assert_called_once_with("catppuccin-mocha")

    def test_set_theme_enabled_invalid(self, selector, enable_themes):
        """Test setting an invalid theme when enabled."""
        result = selector.set_theme("invalid-theme")
        assert "error" in result
        assert result["error"] == "Theme 'invalid-theme' not found"
        selector.engine.save_preference.assert_not_called()

    def test_set_theme_disabled(self, selector, disable_themes):
        """Test setting a theme when disabled."""
        result = selector.set_theme("catppuccin-mocha")
        assert "error" in result
        assert result["error"] == "Themes are disabled"

    def test_get_current_theme_enabled(self, selector, enable_themes):
        """Test getting current theme when enabled."""
        result = selector.get_current_theme()
        assert result == "catppuccin-mocha"
        selector.engine.get_preference.assert_called_once()

    def test_get_current_theme_disabled(self, selector, disable_themes):
        """Test getting current theme when disabled."""
        result = selector.get_current_theme()
        assert isinstance(result, dict)
        assert "error" in result
        assert result["error"] == "Themes are disabled"

    def test_auto_detect_theme_dark_mode(self, selector, enable_themes):
        """Test auto-detecting theme in dark mode."""
        selector.engine.detect_capabilities.return_value = {"dark_mode": True}
        result = selector.auto_detect_theme()
        assert result == "catppuccin-mocha"
        selector.engine.detect_capabilities.assert_called_once()

    def test_auto_detect_theme_light_mode(self, selector, enable_themes):
        """Test auto-detecting theme in light mode."""
        selector.engine.detect_capabilities.return_value = {"dark_mode": False}
        result = selector.auto_detect_theme()
        assert result == "catppuccin-latte"
        selector.engine.detect_capabilities.assert_called_once()

    def test_auto_detect_theme_disabled(self, selector, disable_themes):
        """Test auto-detecting theme when disabled."""
        result = selector.auto_detect_theme()
        assert isinstance(result, dict)
        assert "error" in result
        assert result["error"] == "Themes are disabled"
