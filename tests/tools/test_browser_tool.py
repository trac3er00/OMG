#!/usr/bin/env python3
"""
Tests for tools/browser_tool.py

Tests BrowserSession state tracking, 5 core browser operations
(navigate, click, type, screenshot, evaluate), feature flag gating,
dry-run CLI mode, and tool call spec generation.
"""

import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

# Enable feature flag for tests
os.environ["OMG_BROWSER_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

import browser_tool
from browser_tool import (
    BrowserSession,
    browser_click,
    browser_evaluate,
    browser_navigate,
    browser_screenshot,
    browser_type,
    session,
)


# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_session():
    """Reset the module-level session before each test."""
    session.reset()
    session.current_url = ""
    yield
    session.reset()
    session.current_url = ""


# =============================================================================
# TestBrowserSession — creates session, tracks url, tracks screenshots (3 tests)
# =============================================================================


class TestBrowserSession:
    """Tests for the BrowserSession dataclass."""

    def test_creates_session_with_id(self):
        """BrowserSession initializes with a unique session_id."""
        s = BrowserSession()
        assert isinstance(s.session_id, str)
        assert len(s.session_id) == 12
        assert s.current_url == ""
        assert s.history == []
        assert s.screenshots == []

    def test_tracks_url_navigation(self):
        """navigate_to updates current_url and appends to history."""
        s = BrowserSession()
        s.navigate_to("https://example.com")
        assert s.current_url == "https://example.com"
        assert s.history == ["https://example.com"]

        s.navigate_to("https://example.com/page2")
        assert s.current_url == "https://example.com/page2"
        assert len(s.history) == 2
        assert s.history[1] == "https://example.com/page2"

    def test_tracks_screenshots(self):
        """record_screenshot appends to screenshots list."""
        s = BrowserSession()
        s.record_screenshot("home-page")
        s.record_screenshot("login-form")
        assert s.screenshots == ["home-page", "login-form"]

    def test_to_dict(self):
        """to_dict returns a plain dictionary of session state."""
        s = BrowserSession()
        s.navigate_to("https://test.com")
        d = s.to_dict()
        assert isinstance(d, dict)
        assert d["current_url"] == "https://test.com"
        assert "session_id" in d

    def test_reset(self):
        """reset clears state but keeps session_id."""
        s = BrowserSession()
        sid = s.session_id
        s.navigate_to("https://test.com")
        s.record_screenshot("shot1")
        s.reset()
        assert s.session_id == sid
        assert s.current_url == ""
        assert s.history == []
        assert s.screenshots == []


# =============================================================================
# TestBrowserNavigate — returns spec, dry-run, flag disabled (3 tests)
# =============================================================================


class TestBrowserNavigate:
    """Tests for browser_navigate()."""

    def test_returns_tool_call_spec(self):
        """browser_navigate returns a valid tool call spec dict."""
        result = browser_navigate("https://example.com")
        assert result["success"] is True
        assert result["error"] is None
        spec = result["result"]
        assert spec["tool"] == "mcp_puppeteer_puppeteer_navigate"
        assert spec["parameters"]["url"] == "https://example.com"

    def test_adds_https_scheme(self):
        """browser_navigate adds https:// if missing."""
        result = browser_navigate("example.com")
        assert result["success"] is True
        assert result["result"]["parameters"]["url"] == "https://example.com"

    def test_returns_error_when_disabled(self):
        """browser_navigate returns error when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_ENABLED": "false"}):
            result = browser_navigate("https://example.com")
            assert result["success"] is False
            assert "disabled" in result["error"].lower()

    def test_tracks_session_state(self):
        """browser_navigate updates the module-level session."""
        browser_navigate("https://example.com")
        assert session.current_url == "https://example.com"
        assert "https://example.com" in session.history


# =============================================================================
# TestBrowserClick — returns spec, flag disabled (2 tests)
# =============================================================================


class TestBrowserClick:
    """Tests for browser_click()."""

    def test_returns_tool_call_spec(self):
        """browser_click returns a valid tool call spec dict."""
        result = browser_click("#submit-btn")
        assert result["success"] is True
        spec = result["result"]
        assert spec["tool"] == "mcp_puppeteer_puppeteer_click"
        assert spec["parameters"]["selector"] == "#submit-btn"

    def test_returns_error_when_disabled(self):
        """browser_click returns error when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_ENABLED": "false"}):
            result = browser_click("#btn")
            assert result["success"] is False
            assert "disabled" in result["error"].lower()


# =============================================================================
# TestBrowserType — returns spec, flag disabled (2 tests)
# =============================================================================


class TestBrowserType:
    """Tests for browser_type()."""

    def test_returns_tool_call_spec(self):
        """browser_type returns a valid tool call spec dict."""
        result = browser_type("#email", "user@example.com")
        assert result["success"] is True
        spec = result["result"]
        assert spec["tool"] == "mcp_puppeteer_puppeteer_fill"
        assert spec["parameters"]["selector"] == "#email"
        assert spec["parameters"]["value"] == "user@example.com"

    def test_returns_error_when_disabled(self):
        """browser_type returns error when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_ENABLED": "false"}):
            result = browser_type("#input", "text")
            assert result["success"] is False
            assert "disabled" in result["error"].lower()


# =============================================================================
# TestBrowserScreenshot — returns spec, flag disabled (2 tests)
# =============================================================================


class TestBrowserScreenshot:
    """Tests for browser_screenshot()."""

    def test_returns_tool_call_spec(self):
        """browser_screenshot returns a valid tool call spec with optional selector."""
        result = browser_screenshot("homepage", selector=".main-content")
        assert result["success"] is True
        spec = result["result"]
        assert spec["tool"] == "mcp_puppeteer_puppeteer_screenshot"
        assert spec["parameters"]["name"] == "homepage"
        assert spec["parameters"]["selector"] == ".main-content"

    def test_returns_spec_without_selector(self):
        """browser_screenshot works without a selector."""
        result = browser_screenshot("full-page")
        assert result["success"] is True
        assert "selector" not in result["result"]["parameters"]

    def test_returns_error_when_disabled(self):
        """browser_screenshot returns error when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_ENABLED": "false"}):
            result = browser_screenshot("shot")
            assert result["success"] is False
            assert "disabled" in result["error"].lower()

    def test_tracks_screenshot_in_session(self):
        """browser_screenshot records screenshot name in session."""
        browser_screenshot("my-shot")
        assert "my-shot" in session.screenshots


# =============================================================================
# TestBrowserEvaluate — returns spec, flag disabled (2 tests)
# =============================================================================


class TestBrowserEvaluate:
    """Tests for browser_evaluate()."""

    def test_returns_tool_call_spec(self):
        """browser_evaluate returns a valid tool call spec dict."""
        result = browser_evaluate("document.title")
        assert result["success"] is True
        spec = result["result"]
        assert spec["tool"] == "mcp_puppeteer_puppeteer_evaluate"
        assert spec["parameters"]["script"] == "document.title"

    def test_returns_error_when_disabled(self):
        """browser_evaluate returns error when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_ENABLED": "false"}):
            result = browser_evaluate("1+1")
            assert result["success"] is False
            assert "disabled" in result["error"].lower()


# =============================================================================
# TestCLI — dry-run mode, flag disabled output (2 tests)
# =============================================================================


class TestCLI:
    """Tests for CLI interface."""

    def test_dry_run_navigate(self):
        """--dry-run --navigate prints tool spec without executing."""
        result = subprocess.run(
            [
                sys.executable, "-m", "browser_tool",
                "--navigate", "https://example.com",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tools_dir,
            env={**os.environ, "OMG_BROWSER_ENABLED": "true"},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["dry_run"] is True
        assert output["operation"] == "navigate"
        assert output["url"] == "https://example.com"
        assert output["spec"]["success"] is True

    def test_flag_disabled_output(self):
        """CLI shows error when feature flag is disabled."""
        result = subprocess.run(
            [
                sys.executable, "-m", "browser_tool",
                "--navigate", "https://example.com",
            ],
            capture_output=True,
            text=True,
            cwd=tools_dir,
            env={**os.environ, "OMG_BROWSER_ENABLED": "false"},
        )
        assert result.returncode != 0
        output = json.loads(result.stdout)
        assert "error" in output
        assert "disabled" in output["error"].lower()
