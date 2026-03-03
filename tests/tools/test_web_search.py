#!/usr/bin/env python3
"""
Tests for tools/web_search.py

Tests provider abstraction, SearchResult dataclass, WebSearchManager,
credential lookup, and CLI interface.
"""

import json
import os
import subprocess
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# Enable feature flag for tests
os.environ["OAL_WEB_SEARCH_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

import web_search
from web_search import (
    Provider,
    SearchResult,
    WebSearchManager,
    get_api_key,
    manager,
)


# --- Concrete test provider ---


class MockProvider(Provider):
    """A concrete provider for testing."""

    def __init__(self, results: List[Dict[str, str]] = None, fetch_content: str = ""):
        self._results = results or []
        self._fetch_content = fetch_content

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        return self._results

    def fetch(self, url: str) -> str:
        return self._fetch_content


class FailingProvider(Provider):
    """A provider that always raises exceptions."""

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        raise ConnectionError("Search failed")

    def fetch(self, url: str) -> str:
        raise ConnectionError("Fetch failed")


# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_manager():
    """Reset the module-level manager before each test."""
    manager._providers.clear()
    manager._default_provider = None
    yield
    manager._providers.clear()
    manager._default_provider = None


# =============================================================================
# TestProvider — abstract class, search interface, fetch interface (3 tests)
# =============================================================================


class TestProvider:
    """Tests for the abstract Provider base class."""

    def test_cannot_instantiate_abstract(self):
        """Provider cannot be instantiated directly — it's abstract."""
        with pytest.raises(TypeError):
            Provider()

    def test_search_interface(self):
        """Concrete provider's search() returns list of dicts."""
        prov = MockProvider(results=[
            {"title": "Result 1", "url": "https://example.com", "snippet": "Snippet 1"},
        ])
        results = prov.search("test query")
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["title"] == "Result 1"

    def test_fetch_interface(self):
        """Concrete provider's fetch() returns string content."""
        prov = MockProvider(fetch_content="<html>Hello</html>")
        content = prov.fetch("https://example.com")
        assert isinstance(content, str)
        assert "Hello" in content

    def test_provider_name_property(self):
        """Provider name defaults to lowercase class name."""
        prov = MockProvider()
        assert prov.name == "mockprovider"


# =============================================================================
# TestSearchResult — dataclass fields, from_dict constructor (2 tests)
# =============================================================================


class TestSearchResult:
    """Tests for the SearchResult dataclass."""

    def test_dataclass_fields(self):
        """SearchResult has title, url, snippet, source fields."""
        result = SearchResult(
            title="Test Title",
            url="https://example.com",
            snippet="A snippet",
            source="exa",
        )
        assert result.title == "Test Title"
        assert result.url == "https://example.com"
        assert result.snippet == "A snippet"
        assert result.source == "exa"

    def test_from_dict_constructor(self):
        """SearchResult.from_dict creates instance from a dictionary."""
        data = {
            "title": "Dict Title",
            "url": "https://test.com",
            "snippet": "Dict snippet",
            "source": "serper",
        }
        result = SearchResult.from_dict(data)
        assert result.title == "Dict Title"
        assert result.url == "https://test.com"
        assert result.source == "serper"

    def test_from_dict_missing_keys(self):
        """SearchResult.from_dict handles missing keys with defaults."""
        result = SearchResult.from_dict({"title": "Only Title"})
        assert result.title == "Only Title"
        assert result.url == ""
        assert result.snippet == ""
        assert result.source == ""

    def test_to_dict(self):
        """SearchResult.to_dict returns a plain dictionary."""
        result = SearchResult(
            title="T", url="U", snippet="S", source="P"
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["title"] == "T"
        assert d["source"] == "P"


# =============================================================================
# TestWebSearchManager — register, search, get_providers, flag disabled (4 tests)
# =============================================================================


class TestWebSearchManager:
    """Tests for WebSearchManager."""

    def test_register_provider(self):
        """register_provider adds provider and sets it as default."""
        mgr = WebSearchManager()
        prov = MockProvider()
        mgr.register_provider("mock", prov)
        assert "mock" in mgr.get_providers()
        assert mgr._default_provider == "mock"

    def test_search_dispatches_to_provider(self):
        """search() dispatches to the correct registered provider."""
        mgr = WebSearchManager()
        prov = MockProvider(results=[
            {"title": "R1", "url": "https://a.com", "snippet": "S1"},
            {"title": "R2", "url": "https://b.com", "snippet": "S2"},
        ])
        mgr.register_provider("test_prov", prov)
        results = mgr.search("hello world")
        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "R1"
        assert results[0].source == "test_prov"

    def test_get_providers_list(self):
        """get_providers returns registered provider names."""
        mgr = WebSearchManager()
        mgr.register_provider("alpha", MockProvider())
        mgr.register_provider("beta", MockProvider())
        providers = mgr.get_providers()
        assert providers == ["alpha", "beta"]

    def test_search_returns_empty_when_disabled(self):
        """search() returns empty list when feature flag is disabled."""
        mgr = WebSearchManager()
        mgr.register_provider("mock", MockProvider(results=[
            {"title": "R", "url": "U", "snippet": "S"},
        ]))
        with patch.dict(os.environ, {"OAL_WEB_SEARCH_ENABLED": "false"}):
            results = mgr.search("test")
            assert results == []

    def test_search_with_named_provider(self):
        """search() can target a specific provider by name."""
        mgr = WebSearchManager()
        mgr.register_provider("a", MockProvider(results=[
            {"title": "From A", "url": "U", "snippet": "S"},
        ]))
        mgr.register_provider("b", MockProvider(results=[
            {"title": "From B", "url": "U", "snippet": "S"},
        ]))
        results = mgr.search("q", provider="b")
        assert results[0].title == "From B"

    def test_search_handles_provider_error(self):
        """search() returns empty list when provider raises exception."""
        mgr = WebSearchManager()
        mgr.register_provider("fail", FailingProvider())
        results = mgr.search("test")
        assert results == []

    def test_unregister_provider(self):
        """unregister_provider removes provider and updates default."""
        mgr = WebSearchManager()
        mgr.register_provider("a", MockProvider())
        mgr.register_provider("b", MockProvider())
        assert mgr.unregister_provider("a") is True
        assert "a" not in mgr.get_providers()
        assert mgr._default_provider == "b"

    def test_fetch_dispatches(self):
        """fetch() dispatches to the correct provider."""
        mgr = WebSearchManager()
        mgr.register_provider("fp", MockProvider(fetch_content="fetched!"))
        content = mgr.fetch("https://example.com")
        assert content == "fetched!"

    def test_fetch_returns_empty_when_disabled(self):
        """fetch() returns empty string when feature flag disabled."""
        mgr = WebSearchManager()
        mgr.register_provider("fp", MockProvider(fetch_content="content"))
        with patch.dict(os.environ, {"OAL_WEB_SEARCH_ENABLED": "false"}):
            assert mgr.fetch("https://example.com") == ""


# =============================================================================
# TestCredentialLookup — env var fallback, credential store integration (2 tests)
# =============================================================================


class TestCredentialLookup:
    """Tests for get_api_key credential lookup."""

    def test_env_var_fallback(self):
        """get_api_key falls back to env var {PROVIDER}_API_KEY."""
        # Ensure credential store path returns None
        with patch.object(web_search, "_HAS_CREDENTIAL_STORE", False):
            with patch.dict(os.environ, {"EXA_API_KEY": "test-key-123"}):
                key = get_api_key("exa")
                assert key == "test-key-123"

    def test_credential_store_integration(self):
        """get_api_key tries credential_store first if available."""
        mock_store = MagicMock()
        mock_store.get_active_key.return_value = "store-key-456"

        with patch.object(web_search, "_HAS_CREDENTIAL_STORE", True):
            with patch.object(web_search, "_credential_store", mock_store):
                key = get_api_key("exa")
                assert key == "store-key-456"
                mock_store.get_active_key.assert_called_once_with("exa")

    def test_credential_store_fallback_on_none(self):
        """get_api_key falls back to env var if credential_store returns None."""
        mock_store = MagicMock()
        mock_store.get_active_key.return_value = None

        with patch.object(web_search, "_HAS_CREDENTIAL_STORE", True):
            with patch.object(web_search, "_credential_store", mock_store):
                with patch.dict(os.environ, {"SERPER_API_KEY": "env-key-789"}):
                    key = get_api_key("serper")
                    assert key == "env-key-789"


# =============================================================================
# TestCLI — dry-run mode, flag disabled output (2 tests)
# =============================================================================


class TestCLI:
    """Tests for CLI interface."""

    def test_dry_run_mode(self):
        """--dry-run --query prints search plan without executing."""
        result = subprocess.run(
            [
                sys.executable, "-m", "web_search",
                "--query", "test query",
                "--provider", "exa",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tools_dir,
            env={**os.environ, "OAL_WEB_SEARCH_ENABLED": "true"},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["dry_run"] is True
        assert output["query"] == "test query"
        assert output["provider"] == "exa"

    def test_flag_disabled_output(self):
        """CLI shows error when feature flag is disabled."""
        result = subprocess.run(
            [
                sys.executable, "-m", "web_search",
                "--query", "test",
            ],
            capture_output=True,
            text=True,
            cwd=tools_dir,
            env={**os.environ, "OAL_WEB_SEARCH_ENABLED": "false"},
        )
        assert result.returncode != 0
        output = json.loads(result.stdout)
        assert "error" in output
        assert "disabled" in output["error"].lower()
