#!/usr/bin/env python3
"""
Puppeteer Browser Integration for OMG

Wrapper around Puppeteer MCP tools that generates tool call specifications
for browser automation. Functions produce spec dicts — actual execution is
done by Claude Code when it dispatches the MCP call.

Feature flag: OMG_BROWSER_ENABLED (default: False)
"""

import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# --- Lazy imports for hooks/_common.py ---

_get_feature_flag = None


def _ensure_imports():
    """Lazy import feature flag from hooks/_common.py."""
    global _get_feature_flag
    if _get_feature_flag is not None:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from hooks._common import get_feature_flag as _gff
        _get_feature_flag = _gff
    except ImportError:
        pass


# --- Feature flag ---

def _is_enabled() -> bool:
    """Check if Browser feature is enabled."""
    # Fast path: check env var directly
    env_val = os.environ.get("OMG_BROWSER_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    # Fallback to hooks/_common.get_feature_flag
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("BROWSER", default=False)
    return False


# --- Response helpers ---

def _success_response(result: Any) -> Dict[str, Any]:
    """Create a success response dict."""
    return {"success": True, "result": result, "error": None}


def _error_response(error: str) -> Dict[str, Any]:
    """Create an error response dict."""
    return {"success": False, "result": None, "error": error}


def _disabled_response() -> Dict[str, Any]:
    """Create a response for when the feature flag is disabled."""
    return _error_response("Browser feature is disabled (OMG_BROWSER_ENABLED=false)")


# =============================================================================
# BrowserSession — session state tracking
# =============================================================================


@dataclass
class BrowserSession:
    """Manages browser session state.

    Tracks the current URL, navigation history, and screenshot names
    for the duration of a browser automation session.

    Attributes:
        session_id: Unique identifier for this session.
        current_url: The URL the browser is currently on (empty if none).
        history: List of URLs visited during this session.
        screenshots: List of screenshot names taken during this session.
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    current_url: str = ""
    history: List[str] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)

    def navigate_to(self, url: str) -> None:
        """Record a navigation to a URL."""
        self.current_url = url
        self.history.append(url)

    def record_screenshot(self, name: str) -> None:
        """Record a screenshot taken."""
        self.screenshots.append(name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session state to a plain dictionary."""
        return asdict(self)

    def reset(self) -> None:
        """Reset session state while keeping the same session_id."""
        self.current_url = ""
        self.history.clear()
        self.screenshots.clear()


# Module-level session instance
session = BrowserSession()


# =============================================================================
# Browser Operations — tool call spec generators
# =============================================================================


def browser_navigate(url: str, timeout: int = 30) -> Dict[str, Any]:
    """Navigate the browser to a URL.

    Generates a Puppeteer MCP tool call spec for navigation.

    Args:
        url: The URL to navigate to.
        timeout: Navigation timeout in seconds (default: 30).

    Returns:
        A dict with ``success``, ``result`` (the tool call spec), and ``error``.
        If the feature flag is disabled, returns an error response.
    """
    if not _is_enabled():
        return _disabled_response()

    try:
        if not url or not isinstance(url, str):
            return _error_response("URL must be a non-empty string")

        # Validate URL has a scheme
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        spec = {
            "tool": "mcp_puppeteer_puppeteer_navigate",
            "parameters": {
                "url": url,
            },
        }

        # Track session state
        session.navigate_to(url)

        return _success_response(spec)

    except Exception as e:
        return _error_response(str(e))


def browser_click(selector: str) -> Dict[str, Any]:
    """Click an element on the page.

    Generates a Puppeteer MCP tool call spec for clicking.

    Args:
        selector: CSS selector for the element to click.

    Returns:
        A dict with ``success``, ``result`` (the tool call spec), and ``error``.
    """
    if not _is_enabled():
        return _disabled_response()

    try:
        if not selector or not isinstance(selector, str):
            return _error_response("Selector must be a non-empty string")

        spec = {
            "tool": "mcp_puppeteer_puppeteer_click",
            "parameters": {
                "selector": selector,
            },
        }

        return _success_response(spec)

    except Exception as e:
        return _error_response(str(e))


def browser_type(selector: str, text: str) -> Dict[str, Any]:
    """Type text into an input element.

    Generates a Puppeteer MCP tool call spec for filling an input field.

    Args:
        selector: CSS selector for the input field.
        text: The text to type into the field.

    Returns:
        A dict with ``success``, ``result`` (the tool call spec), and ``error``.
    """
    if not _is_enabled():
        return _disabled_response()

    try:
        if not selector or not isinstance(selector, str):
            return _error_response("Selector must be a non-empty string")
        if not isinstance(text, str):
            return _error_response("Text must be a string")

        spec = {
            "tool": "mcp_puppeteer_puppeteer_fill",
            "parameters": {
                "selector": selector,
                "value": text,
            },
        }

        return _success_response(spec)

    except Exception as e:
        return _error_response(str(e))


def browser_screenshot(name: str, selector: Optional[str] = None) -> Dict[str, Any]:
    """Take a screenshot of the page or a specific element.

    Generates a Puppeteer MCP tool call spec for taking a screenshot.

    Args:
        name: Name for the screenshot.
        selector: Optional CSS selector for a specific element to capture.

    Returns:
        A dict with ``success``, ``result`` (the tool call spec), and ``error``.
    """
    if not _is_enabled():
        return _disabled_response()

    try:
        if not name or not isinstance(name, str):
            return _error_response("Name must be a non-empty string")

        params: Dict[str, Any] = {"name": name}
        if selector:
            params["selector"] = selector

        spec = {
            "tool": "mcp_puppeteer_puppeteer_screenshot",
            "parameters": params,
        }

        # Track screenshot
        session.record_screenshot(name)

        return _success_response(spec)

    except Exception as e:
        return _error_response(str(e))


def browser_evaluate(script: str) -> Dict[str, Any]:
    """Execute JavaScript in the browser console.

    Generates a Puppeteer MCP tool call spec for evaluating JavaScript.

    Args:
        script: JavaScript code to execute.

    Returns:
        A dict with ``success``, ``result`` (the tool call spec), and ``error``.
    """
    if not _is_enabled():
        return _disabled_response()

    try:
        if not script or not isinstance(script, str):
            return _error_response("Script must be a non-empty string")

        spec = {
            "tool": "mcp_puppeteer_puppeteer_evaluate",
            "parameters": {
                "script": script,
            },
        }

        return _success_response(spec)

    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# CLI Interface
# =============================================================================


def _cli_main():
    """CLI entry point for browser_tool.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG Browser Tool — Puppeteer MCP wrapper for browser automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--navigate", dest="navigate_url", help="Navigate to URL")
    parser.add_argument("--click", dest="click_selector", help="Click CSS selector")
    parser.add_argument(
        "--type", dest="type_args", nargs=2, metavar=("SELECTOR", "TEXT"),
        help="Type text into selector",
    )
    parser.add_argument(
        "--screenshot", dest="screenshot_name", help="Take screenshot with name",
    )
    parser.add_argument(
        "--screenshot-selector", dest="screenshot_selector", default=None,
        help="Optional CSS selector for screenshot (use with --screenshot)",
    )
    parser.add_argument("--evaluate", dest="eval_script", help="Evaluate JavaScript")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the tool call spec without executing",
    )
    parser.add_argument(
        "--session-info", action="store_true",
        help="Show current session state",
    )

    args = parser.parse_args()

    enabled = _is_enabled()

    # Session info
    if args.session_info:
        print(json.dumps({
            "session": session.to_dict(),
            "enabled": enabled,
        }, indent=2))
        return

    # Dry-run navigate
    if args.dry_run and args.navigate_url:
        result = browser_navigate(args.navigate_url)
        print(json.dumps({
            "dry_run": True,
            "operation": "navigate",
            "url": args.navigate_url,
            "enabled": enabled,
            "spec": result,
        }, indent=2))
        return

    # Dry-run click
    if args.dry_run and args.click_selector:
        result = browser_click(args.click_selector)
        print(json.dumps({
            "dry_run": True,
            "operation": "click",
            "selector": args.click_selector,
            "enabled": enabled,
            "spec": result,
        }, indent=2))
        return

    # Dry-run type
    if args.dry_run and args.type_args:
        result = browser_type(args.type_args[0], args.type_args[1])
        print(json.dumps({
            "dry_run": True,
            "operation": "type",
            "selector": args.type_args[0],
            "text": args.type_args[1],
            "enabled": enabled,
            "spec": result,
        }, indent=2))
        return

    # Dry-run screenshot
    if args.dry_run and args.screenshot_name:
        result = browser_screenshot(args.screenshot_name, args.screenshot_selector)
        print(json.dumps({
            "dry_run": True,
            "operation": "screenshot",
            "name": args.screenshot_name,
            "selector": args.screenshot_selector,
            "enabled": enabled,
            "spec": result,
        }, indent=2))
        return

    # Dry-run evaluate
    if args.dry_run and args.eval_script:
        result = browser_evaluate(args.eval_script)
        print(json.dumps({
            "dry_run": True,
            "operation": "evaluate",
            "script": args.eval_script,
            "enabled": enabled,
            "spec": result,
        }, indent=2))
        return

    # Non-dry-run: check feature flag
    if not enabled:
        print(json.dumps({
            "error": "Browser feature is disabled (OMG_BROWSER_ENABLED=false)",
        }))
        sys.exit(1)

    # Execute operations
    if args.navigate_url:
        result = browser_navigate(args.navigate_url)
        print(json.dumps(result, indent=2))
        return

    if args.click_selector:
        result = browser_click(args.click_selector)
        print(json.dumps(result, indent=2))
        return

    if args.type_args:
        result = browser_type(args.type_args[0], args.type_args[1])
        print(json.dumps(result, indent=2))
        return

    if args.screenshot_name:
        result = browser_screenshot(args.screenshot_name, args.screenshot_selector)
        print(json.dumps(result, indent=2))
        return

    if args.eval_script:
        result = browser_evaluate(args.eval_script)
        print(json.dumps(result, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
