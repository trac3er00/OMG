import os
import sys
import json
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

def is_themes_enabled() -> bool:
    """Lazy import feature flag."""
    try:
        from hooks._common import get_feature_flag
        return get_feature_flag("THEMES", default=False)
    except ImportError:
        return os.environ.get("OAL_THEMES_ENABLED", "").lower() in ("1", "true", "yes")

try:
    from tools.theme_engine import ThemeEngine, Theme
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.theme_engine import ThemeEngine, Theme

class ThemeSelector:
    """Interactive theme selection, preview, and auto-detection."""

    def __init__(self, engine: Optional[ThemeEngine] = None):
        self.engine = engine or ThemeEngine()

    def list_themes(self) -> Union[List[str], Dict[str, str]]:
        """Returns sorted list of available theme names."""
        if not is_themes_enabled():
            return {"error": "Themes are disabled"}
        return sorted(self.engine.get_available_themes())

    def preview_theme(self, name: str) -> Dict[str, Any]:
        """Returns preview info {name, colors, ansi_preview: str} without applying."""
        if not is_themes_enabled():
            return {"error": "Themes are disabled"}

        theme = self.engine.load_theme(name)
        if not theme:
            return {"error": f"Theme '{name}' not found"}

        ansi_codes = self.engine.apply_theme(theme)
        
        preview_lines = [f"Preview for {theme.name}:"]
        for color_name, hex_val in theme.colors.items():
            ansi = ansi_codes.get(color_name, "")
            reset = "\033[0m" if ansi else ""
            preview_lines.append(f"{ansi}██ {color_name}: {hex_val}{reset}")
            
        return {
            "name": theme.name,
            "colors": theme.colors,
            "ansi_preview": "\n".join(preview_lines)
        }

    def set_theme(self, name: str) -> Dict[str, Any]:
        """Applies + persists theme, returns {success, theme, applied_at}."""
        if not is_themes_enabled():
            return {"error": "Themes are disabled"}

        theme = self.engine.load_theme(name)
        if not theme:
            return {"error": f"Theme '{name}' not found"}

        self.engine.apply_theme(theme)
        success = self.engine.save_preference(name)
        
        return {
            "success": success,
            "theme": theme.name,
            "applied_at": datetime.now(timezone.utc).isoformat()
        }

    def get_current_theme(self) -> Union[Optional[str], Dict[str, str]]:
        """Reads current theme from .oal/state/theme.json."""
        if not is_themes_enabled():
            return {"error": "Themes are disabled"}
        return self.engine.get_preference()

    def auto_detect_theme(self) -> Union[str, Dict[str, str]]:
        """Detects dark/light mode, returns appropriate default theme name."""
        if not is_themes_enabled():
            return {"error": "Themes are disabled"}
            
        caps = self.engine.detect_capabilities()
        if caps.get("dark_mode", True):
            return "catppuccin-mocha"
        else:
            return "catppuccin-latte"

def main():
    parser = argparse.ArgumentParser(description="OAL Theme Selector")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List available themes")
    group.add_argument("--preview", type=str, metavar="NAME", help="Preview a theme")
    group.add_argument("--set", type=str, metavar="NAME", help="Set a theme")
    group.add_argument("--auto", action="store_true", help="Auto-detect theme")
    group.add_argument("--current", action="store_true", help="Get current theme")

    args = parser.parse_args()
    
    selector = ThemeSelector()

    if args.list:
        result = selector.list_themes()
        if isinstance(result, dict) and "error" in result:
            print(json.dumps(result))
            sys.exit(1)
        for theme in result:
            print(theme)
    elif args.preview:
        result = selector.preview_theme(args.preview)
        if "error" in result:
            print(json.dumps(result))
            sys.exit(1)
        print(result["ansi_preview"])
    elif args.set:
        result = selector.set_theme(args.set)
        print(json.dumps(result))
        if "error" in result or not result.get("success"):
            sys.exit(1)
    elif args.auto:
        result = selector.auto_detect_theme()
        if isinstance(result, dict) and "error" in result:
            print(json.dumps(result))
            sys.exit(1)
        print(result)
    elif args.current:
        result = selector.get_current_theme()
        if isinstance(result, dict) and "error" in result:
            print(json.dumps(result))
            sys.exit(1)
        print(result if result else "None")

if __name__ == "__main__":
    main()
