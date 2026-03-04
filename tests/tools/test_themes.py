import os
from unittest.mock import patch
import pytest

from tools.theme_engine import ThemeEngine

@pytest.fixture
def enable_themes():
    with patch.dict(os.environ, {"OMG_THEMES_ENABLED": "true"}):
        yield

@pytest.fixture
def engine():
    # Explicitly set project_dir to the root of the repository
    # to avoid issues when running the full test suite where
    # other tests might mock os.getcwd() or CLAUDE_PROJECT_DIR
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return ThemeEngine(project_dir=repo_root)

class TestCoreThemes:
    """Test that all 10 core themes are valid and loadable."""
    
    EXPECTED_THEMES = [
        "catppuccin-mocha",
        "catppuccin-latte",
        "catppuccin-frappe",
        "catppuccin-macchiato",
        "dracula",
        "nord",
        "gruvbox-dark",
        "tokyo-night",
        "one-dark",
        "solarized-dark"
    ]

    def test_all_themes_available(self, enable_themes, engine):
        """Test that get_available_themes returns all expected themes."""
        available = engine.get_available_themes()
        for theme in self.EXPECTED_THEMES:
            assert theme in available, f"Theme {theme} is missing from available themes"

    @pytest.mark.parametrize("theme_name", EXPECTED_THEMES)
    def test_theme_loads_successfully(self, enable_themes, engine, theme_name):
        """Test that each core theme can be loaded and has required fields."""
        theme = engine.load_theme(theme_name)
        
        assert theme is not None, f"Failed to load theme: {theme_name}"
        assert theme.name is not None
        assert theme.variant in ("dark", "light")
        
        # Check required colors
        required_colors = [
            "background", "foreground", "primary", "secondary",
            "accent", "error", "warning", "success"
        ]
        for color in required_colors:
            assert color in theme.colors, f"Theme {theme_name} missing color: {color}"
            assert theme.colors[color].startswith("#"), f"Theme {theme_name} color {color} must be hex"
            assert len(theme.colors[color]) in (4, 7), f"Theme {theme_name} color {color} has invalid hex length"

    def test_catppuccin_mocha_colors(self, enable_themes, engine):
        """Test specific colors for Catppuccin Mocha."""
        theme = engine.load_theme("catppuccin-mocha")
        assert theme.colors["background"] == "#1e1e2e"
        assert theme.colors["foreground"] == "#cdd6f4"
        assert theme.colors["primary"] == "#cba6f7"

    def test_dracula_colors(self, enable_themes, engine):
        """Test specific colors for Dracula."""
        theme = engine.load_theme("dracula")
        assert theme.colors["background"] == "#282a36"
        assert theme.colors["foreground"] == "#f8f8f2"
        assert theme.colors["primary"] == "#bd93f9"

    def test_nord_colors(self, enable_themes, engine):
        """Test specific colors for Nord."""
        theme = engine.load_theme("nord")
        assert theme.colors["background"] == "#2e3440"
        assert theme.colors["foreground"] == "#d8dee9"
        assert theme.colors["primary"] == "#81a1c1"
