#!/usr/bin/env python3
"""
Theme Engine for OMG

Provides terminal capability detection, theme definition format,
color scheme application, and preference management.

Feature flag: OMG_THEMES_ENABLED (default: False)
"""

import argparse
import datetime
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    # Optional: yaml not available
    _logger.debug("Failed to import yaml module", exc_info=True)
    yaml = None

# --- Lazy imports for hooks/_common.py ---

_get_feature_flag = None
_atomic_json_write = None


def _ensure_imports():
    """Lazy import feature flag and atomic write from hooks/_common.py."""
    global _get_feature_flag, _atomic_json_write
    if _get_feature_flag is not None and _atomic_json_write is not None:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from hooks._common import get_feature_flag as _gff
        from hooks._common import atomic_json_write as _ajw
        if _get_feature_flag is None:
            _get_feature_flag = _gff
        if _atomic_json_write is None:
            _atomic_json_write = _ajw
    except ImportError:
        # Optional: hooks._common not available
        _logger.debug("Failed to import hooks._common helpers", exc_info=True)


def is_themes_enabled() -> bool:
    """Check if themes are enabled via feature flag."""
    _ensure_imports()
    if _get_feature_flag:
        return _get_feature_flag("THEMES", default=False)
    # Fallback if _common.py is not available
    env_val = os.environ.get("OMG_THEMES_ENABLED", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    return False


@dataclass
class Theme:
    """Theme definition."""
    name: str
    variant: str
    colors: Dict[str, str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Theme":
        """Create a Theme from a dictionary."""
        return cls(
            name=data.get("name", "unknown"),
            variant=data.get("variant", "dark"),
            colors=data.get("colors", {}),
            metadata=data.get("metadata", {})
        )


class ThemeEngine:
    """Engine for managing and applying themes."""

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        self.themes_dir = os.path.join(self.project_dir, "config", "themes")
        self.state_file = os.path.join(self.project_dir, ".omg", "state", "theme.json")

    def detect_capabilities(self) -> Dict[str, bool]:
        """Detect terminal capabilities."""
        if not is_themes_enabled():
            return {"truecolor": False, "256color": False, "basic": False, "dark_mode": True}

        colorterm = os.environ.get("COLORTERM", "").lower()
        term = os.environ.get("TERM", "").lower()
        term_program = os.environ.get("TERM_PROGRAM", "").lower()

        truecolor = colorterm in ("truecolor", "24bit")
        color256 = "256color" in term or truecolor
        basic = "color" in term or color256

        # Dark mode detection
        dark_mode = True
        colorfgbg = os.environ.get("COLORFGBG", "")
        if colorfgbg:
            parts = colorfgbg.split(";")
            if len(parts) >= 2:
                try:
                    bg = int(parts[-1])
                    if bg >= 8:
                        dark_mode = False
                except ValueError:
                    _logger.debug("Failed to parse COLORFGBG background value", exc_info=True)
        
        if term_program == "iterm.app":
            # iTerm2 specific detection could go here, but default to dark
            pass

        return {
            "truecolor": truecolor,
            "256color": color256,
            "basic": basic,
            "dark_mode": dark_mode
        }

    def load_theme(self, name: str) -> Optional[Theme]:
        """Load a theme by name from config/themes/."""
        if not is_themes_enabled() or not yaml:
            return None

        theme_path = os.path.join(self.themes_dir, f"{name}.yaml")
        if not os.path.exists(theme_path):
            return None

        try:
            with open(theme_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    return Theme.from_dict(data)
        except Exception:
            _logger.debug("Failed to load theme file", exc_info=True)
        return None

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c + c for c in hex_color)
        if len(hex_color) != 6:
            return (0, 0, 0)
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            return (0, 0, 0)

    def _rgb_to_256(self, r: int, g: int, b: int) -> int:
        """Convert RGB to nearest 256-color index."""
        if r == g == b:
            if r < 8:
                return 16
            if r > 248:
                return 231
            return round(((r - 8) / 247) * 24) + 232

        r_idx = int(round(r / 255.0 * 5))
        g_idx = int(round(g / 255.0 * 5))
        b_idx = int(round(b / 255.0 * 5))
        return 16 + 36 * r_idx + 6 * g_idx + b_idx

    def apply_theme(self, theme: Theme) -> Dict[str, str]:
        """Return ANSI escape codes for the theme colors."""
        if not is_themes_enabled():
            return {}

        caps = self.detect_capabilities()
        if not caps["basic"]:
            return {}

        ansi_codes = {}
        for key, hex_color in theme.colors.items():
            if not hex_color.startswith("#"):
                continue
            
            r, g, b = self._hex_to_rgb(hex_color)
            
            if caps["truecolor"]:
                ansi_codes[key] = f"\033[38;2;{r};{g};{b}m"
            elif caps["256color"]:
                color_idx = self._rgb_to_256(r, g, b)
                ansi_codes[key] = f"\033[38;5;{color_idx}m"
            else:
                # Basic 8-color fallback (simplified)
                ansi_codes[key] = "\033[39m" # Default foreground

        return ansi_codes

    def get_available_themes(self) -> List[str]:
        """List available themes in config/themes/."""
        if not is_themes_enabled() or not os.path.exists(self.themes_dir):
            return []

        themes = []
        try:
            for filename in os.listdir(self.themes_dir):
                if filename.endswith(".yaml") or filename.endswith(".yml"):
                    themes.append(os.path.splitext(filename)[0])
        except OSError:
            _logger.debug("Failed to list available theme files", exc_info=True)
        return sorted(themes)

    def save_preference(self, theme_name: str) -> bool:
        """Save theme preference to .omg/state/theme.json."""
        if not is_themes_enabled():
            return False

        _ensure_imports()
        if not _atomic_json_write:
            return False

        data = {
            "theme": theme_name,
            "set_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        try:
            _atomic_json_write(self.state_file, data)
            return True
        except Exception:
            return False

    def get_preference(self) -> Optional[str]:
        """Read theme preference from .omg/state/theme.json."""
        if not is_themes_enabled():
            return None

        if not os.path.exists(self.state_file):
            return None

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("theme")
        except Exception:
            return None


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="OMG Theme Engine")
    parser.add_argument("--detect-capabilities", action="store_true", help="Detect terminal capabilities")
    parser.add_argument("--list", action="store_true", help="List available themes")
    parser.add_argument("--apply", metavar="THEME", help="Apply a theme and show colors")
    parser.add_argument("--set", metavar="THEME", help="Set theme preference")
    parser.add_argument("--get", action="store_true", help="Get current theme preference")
    
    args = parser.parse_args()
    
    if not is_themes_enabled():
        print("Themes are disabled. Set OMG_THEMES_ENABLED=true to enable.")
        sys.exit(1)
        
    engine = ThemeEngine()
    
    if args.detect_capabilities:
        caps = engine.detect_capabilities()
        print(json.dumps(caps, indent=2))
    elif args.list:
        themes = engine.get_available_themes()
        for theme in themes:
            print(theme)
    elif args.apply:
        theme = engine.load_theme(args.apply)
        if theme:
            codes = engine.apply_theme(theme)
            for name, code in codes.items():
                print(f"{code}{name}\033[0m")
        else:
            print(f"Theme '{args.apply}' not found.")
            sys.exit(1)
    elif args.set:
        if engine.save_preference(args.set):
            print(f"Theme preference set to '{args.set}'")
        else:
            print("Failed to save preference.")
            sys.exit(1)
    elif args.get:
        pref = engine.get_preference()
        if pref:
            print(pref)
        else:
            print("No theme preference set.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
