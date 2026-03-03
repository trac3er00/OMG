#!/usr/bin/env python3
"""
Browser Stealth Plugins for OAL

Provides 14 stealth plugin definitions that can be applied to a browser
session to evade bot detection. Each plugin is a dict with `name`,
`description`, and `js_snippet` fields.

Feature flag: OAL_BROWSER_STEALTH_ENABLED (default: False)
Requires SEPARATE consent: .oal/state/browser_consent.json -> {"consented": true}

IMPORTANT: Stealth plugins are opt-in only. They require:
  1. OAL_BROWSER_ENABLED=true (base browser feature)
  2. OAL_BROWSER_STEALTH_ENABLED=true (stealth feature flag)
  3. Explicit user consent in .oal/state/browser_consent.json
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional


# --- Lazy imports for hooks/_common.py ---

_get_feature_flag = None
_atomic_json_write = None


def _ensure_imports():
    """Lazy import utilities from hooks/_common.py."""
    global _get_feature_flag, _atomic_json_write
    if _get_feature_flag is not None:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from hooks._common import get_feature_flag as _gff
        from hooks._common import atomic_json_write as _ajw
        _get_feature_flag = _gff
        _atomic_json_write = _ajw
    except ImportError:
        pass


# --- Feature flag ---

def _is_stealth_enabled() -> bool:
    """Check if Browser Stealth feature is enabled.

    Requires BOTH OAL_BROWSER_ENABLED and OAL_BROWSER_STEALTH_ENABLED.
    """
    # Check browser base flag first
    browser_env = os.environ.get("OAL_BROWSER_ENABLED", "").lower()
    if browser_env in ("0", "false", "no"):
        return False
    browser_on = browser_env in ("1", "true", "yes")
    if not browser_on:
        _ensure_imports()
        if _get_feature_flag is not None:
            browser_on = _get_feature_flag("BROWSER", default=False)
        if not browser_on:
            return False

    # Check stealth flag
    stealth_env = os.environ.get("OAL_BROWSER_STEALTH_ENABLED", "").lower()
    if stealth_env in ("0", "false", "no"):
        return False
    if stealth_env in ("1", "true", "yes"):
        return True
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("BROWSER_STEALTH", default=False)
    return False


# --- Response helpers ---

def _error_response(error: str, requires_consent: bool = False) -> Dict[str, Any]:
    """Create an error response dict."""
    return {
        "success": False,
        "applied": [],
        "error": error,
        "requires_consent": requires_consent,
    }


def _disabled_response() -> Dict[str, Any]:
    """Response when stealth feature flag is disabled."""
    return _error_response(
        "Browser stealth feature is disabled "
        "(requires OAL_BROWSER_ENABLED=true and OAL_BROWSER_STEALTH_ENABLED=true)"
    )


# =============================================================================
# Stealth Plugin Definitions — 14 plugins
# =============================================================================

STEALTH_PLUGINS: List[Dict[str, str]] = [
    {
        "name": "toString_tampering",
        "description": "Override Function.prototype.toString to hide native code modifications",
        "js_snippet": (
            "const _origToString = Function.prototype.toString;"
            "Function.prototype.toString = function() {"
            "  if (this === Function.prototype.toString) return 'function toString() { [native code] }';"
            "  return _origToString.call(this);"
            "};"
        ),
    },
    {
        "name": "webgl_fingerprint",
        "description": "Spoof WebGL vendor and renderer strings to generic values",
        "js_snippet": (
            "const _getParam = WebGLRenderingContext.prototype.getParameter;"
            "WebGLRenderingContext.prototype.getParameter = function(p) {"
            "  if (p === 0x9245) return 'Intel Inc.';"
            "  if (p === 0x9246) return 'Intel Iris OpenGL Engine';"
            "  return _getParam.call(this, p);"
            "};"
        ),
    },
    {
        "name": "audio_context",
        "description": "Spoof AudioContext fingerprint by adding noise to getFloatFrequencyData",
        "js_snippet": (
            "const _getFloat = AnalyserNode.prototype.getFloatFrequencyData;"
            "AnalyserNode.prototype.getFloatFrequencyData = function(arr) {"
            "  _getFloat.call(this, arr);"
            "  for (let i = 0; i < arr.length; i++) arr[i] += Math.random() * 0.0001;"
            "};"
        ),
    },
    {
        "name": "screen_dimensions",
        "description": "Spoof screen width/height to common desktop resolution",
        "js_snippet": (
            "Object.defineProperty(screen, 'width', {get: () => 1920});"
            "Object.defineProperty(screen, 'height', {get: () => 1080});"
            "Object.defineProperty(screen, 'availWidth', {get: () => 1920});"
            "Object.defineProperty(screen, 'availHeight', {get: () => 1040});"
        ),
    },
    {
        "name": "font_enumeration",
        "description": "Mock document.fonts.check to report a standard font list",
        "js_snippet": (
            "if (document.fonts && document.fonts.check) {"
            "  const _stdFonts = ['Arial','Helvetica','Times New Roman','Courier New','Verdana'];"
            "  document.fonts.check = function(font) {"
            "    return _stdFonts.some(f => font.includes(f));"
            "  };"
            "}"
        ),
    },
    {
        "name": "plugin_mime_types",
        "description": "Mock navigator.plugins and navigator.mimeTypes to appear as a real browser",
        "js_snippet": (
            "Object.defineProperty(navigator, 'plugins', {"
            "  get: () => [{"
            "    name: 'Chrome PDF Plugin',"
            "    description: 'Portable Document Format',"
            "    filename: 'internal-pdf-viewer',"
            "    length: 1"
            "  }]"
            "});"
            "Object.defineProperty(navigator, 'mimeTypes', {"
            "  get: () => [{type: 'application/pdf', suffixes: 'pdf', description: 'PDF'}]"
            "});"
        ),
    },
    {
        "name": "hardware_concurrency",
        "description": "Spoof navigator.hardwareConcurrency to a common value",
        "js_snippet": (
            "Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});"
        ),
    },
    {
        "name": "codec_availability",
        "description": "Mask supported codec list by overriding MediaSource.isTypeSupported",
        "js_snippet": (
            "if (typeof MediaSource !== 'undefined') {"
            "  const _isType = MediaSource.isTypeSupported;"
            "  MediaSource.isTypeSupported = function(mimeType) {"
            "    if (mimeType.includes('webm')) return true;"
            "    if (mimeType.includes('mp4')) return true;"
            "    return _isType.call(this, mimeType);"
            "  };"
            "}"
        ),
    },
    {
        "name": "iframe_detection",
        "description": "Evade iframe-based bot detection by spoofing window.parent and top",
        "js_snippet": (
            "try {"
            "  Object.defineProperty(window, 'parent', {get: () => window});"
            "  Object.defineProperty(window, 'top', {get: () => window});"
            "} catch(e) {}"
        ),
    },
    {
        "name": "locale_spoofing",
        "description": "Spoof navigator.language and navigator.languages to en-US",
        "js_snippet": (
            "Object.defineProperty(navigator, 'language', {get: () => 'en-US'});"
            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
        ),
    },
    {
        "name": "worker_detection",
        "description": "Evade web worker fingerprinting by wrapping Worker constructor",
        "js_snippet": (
            "const _OrigWorker = window.Worker;"
            "window.Worker = function(url, opts) {"
            "  return new _OrigWorker(url, opts);"
            "};"
            "window.Worker.prototype = _OrigWorker.prototype;"
            "window.Worker.toString = () => 'function Worker() { [native code] }';"
        ),
    },
    {
        "name": "canvas_fingerprint",
        "description": "Spoof canvas toDataURL by injecting imperceptible noise",
        "js_snippet": (
            "const _toDataURL = HTMLCanvasElement.prototype.toDataURL;"
            "HTMLCanvasElement.prototype.toDataURL = function(type) {"
            "  const ctx = this.getContext('2d');"
            "  if (ctx) {"
            "    const imgData = ctx.getImageData(0, 0, this.width, this.height);"
            "    for (let i = 0; i < imgData.data.length; i += 4) {"
            "      imgData.data[i] ^= 1;"
            "    }"
            "    ctx.putImageData(imgData, 0, 0);"
            "  }"
            "  return _toDataURL.call(this, type);"
            "};"
        ),
    },
    {
        "name": "battery_status",
        "description": "Spoof navigator.getBattery to return a plausible battery status",
        "js_snippet": (
            "navigator.getBattery = async function() {"
            "  return {"
            "    charging: true,"
            "    chargingTime: 0,"
            "    dischargingTime: Infinity,"
            "    level: 0.87,"
            "    addEventListener: function() {},"
            "    removeEventListener: function() {}"
            "  };"
            "};"
        ),
    },
    {
        "name": "media_devices",
        "description": "Spoof mediaDevices.enumerateDevices to return standard device list",
        "js_snippet": (
            "if (navigator.mediaDevices) {"
            "  navigator.mediaDevices.enumerateDevices = async function() {"
            "    return ["
            "      {deviceId: 'default', kind: 'audioinput', label: '', groupId: 'g1'},"
            "      {deviceId: 'default', kind: 'videoinput', label: '', groupId: 'g2'},"
            "      {deviceId: 'default', kind: 'audiooutput', label: '', groupId: 'g3'}"
            "    ];"
            "  };"
            "}"
        ),
    },
]

# Build name-to-plugin index for O(1) lookup
_PLUGIN_INDEX: Dict[str, Dict[str, str]] = {p["name"]: p for p in STEALTH_PLUGINS}


# =============================================================================
# StealthManager — manages stealth plugin lifecycle
# =============================================================================


class StealthManager:
    """Manages browser stealth plugin definitions and application.

    All operations check the feature flag gate. Plugin application also
    requires explicit user consent via .oal/state/browser_consent.json.

    Attributes:
        project_dir: Root directory containing the .oal/ state folder.
    """

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = project_dir or os.environ.get(
            "CLAUDE_PROJECT_DIR", os.getcwd()
        )

    def get_plugins(self) -> List[Dict[str, str]]:
        """Return all 14 stealth plugin definitions.

        Returns:
            List of plugin dicts, or empty list if feature is disabled.
        """
        if not _is_stealth_enabled():
            return []
        return list(STEALTH_PLUGINS)

    def get_plugin(self, name: str) -> Optional[Dict[str, str]]:
        """Return a single plugin definition by name.

        Args:
            name: The plugin name (e.g. 'canvas_fingerprint').

        Returns:
            Plugin dict if found and feature enabled, None otherwise.
        """
        if not _is_stealth_enabled():
            return None
        return _PLUGIN_INDEX.get(name)

    def is_consented(self) -> bool:
        """Check if user has given explicit consent for stealth plugins.

        Delegates to ConsentManager from browser_consent module.

        Returns:
            True if consent file exists and consented is True, False otherwise.
        """
        try:
            from browser_consent import ConsentManager as _CM
            return _CM(project_dir=self.project_dir).is_consented()
        except ImportError:
            # Fallback: inline check if browser_consent not available
            consent_path = os.path.join(
                self.project_dir, ".oal", "state", "browser_consent.json"
            )
            try:
                if not os.path.exists(consent_path):
                    return False
                with open(consent_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("consented", False) is True
            except (json.JSONDecodeError, OSError, TypeError):
                return False
    def apply_plugins(
        self,
        session: Any,
        plugin_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Apply stealth plugins to a browser session spec.

        Generates a list of JavaScript snippets to inject. Does NOT make
        actual browser calls — returns a spec dict for the caller to execute.

        Args:
            session: A BrowserSession instance (used for context/validation).
            plugin_names: Optional list of plugin names to apply.
                If None, applies all 14 plugins.

        Returns:
            Dict with keys:
              - success: bool
              - applied: list[str] — names of applied plugins
              - error: str|None
              - requires_consent: bool
        """
        # Gate 1: Feature flag
        if not _is_stealth_enabled():
            return _disabled_response()

        # Gate 2: Consent check
        if not self.is_consented():
            return _error_response(
                "Browser stealth requires explicit consent. "
                "Write {\"consented\": true} to .oal/state/browser_consent.json",
                requires_consent=True,
            )

        # Determine which plugins to apply
        if plugin_names is None:
            plugins_to_apply = list(STEALTH_PLUGINS)
        else:
            plugins_to_apply = []
            for name in plugin_names:
                plugin = _PLUGIN_INDEX.get(name)
                if plugin is None:
                    return _error_response(f"Unknown plugin: {name}")
                plugins_to_apply.append(plugin)

        # Build injection specs
        applied_names = [p["name"] for p in plugins_to_apply]
        snippets = [p["js_snippet"] for p in plugins_to_apply]

        return {
            "success": True,
            "applied": applied_names,
            "error": None,
            "requires_consent": False,
            "snippets": snippets,
        }


# =============================================================================
# CLI Interface
# =============================================================================


def _cli_main():
    """CLI entry point for browser_stealth.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OAL Browser Stealth — stealth plugin manager for bot detection evasion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_plugins",
        help="List all stealth plugin definitions",
    )
    parser.add_argument(
        "--get", dest="get_name",
        help="Get a single plugin by name",
    )
    parser.add_argument(
        "--check-consent", action="store_true",
        help="Check if stealth consent has been granted",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show stealth feature status",
    )

    args = parser.parse_args()
    manager = StealthManager()

    if args.status:
        print(json.dumps({
            "stealth_enabled": _is_stealth_enabled(),
            "consented": manager.is_consented(),
            "plugin_count": len(STEALTH_PLUGINS),
        }, indent=2))
        return

    if args.check_consent:
        consented = manager.is_consented()
        print(json.dumps({"consented": consented}, indent=2))
        return

    if args.list_plugins:
        plugins = manager.get_plugins()
        if not plugins:
            print(json.dumps({
                "error": "Stealth feature is disabled",
                "plugins": [],
            }, indent=2))
        else:
            print(json.dumps({
                "count": len(plugins),
                "plugins": [{"name": p["name"], "description": p["description"]} for p in plugins],
            }, indent=2))
        return

    if args.get_name:
        plugin = manager.get_plugin(args.get_name)
        if plugin is None:
            print(json.dumps({
                "error": f"Plugin not found or feature disabled: {args.get_name}",
            }, indent=2))
        else:
            print(json.dumps(plugin, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
