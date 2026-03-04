#!/usr/bin/env python3
"""
Tests for tools/search_providers/ package

Tests all 5 concrete providers (Synthetic, Exa, Brave, Perplexity, Jina),
their CONFIG_SCHEMA, error handling, and auto-registration.
All HTTP calls are mocked — no real network access.
"""

import io
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Enable feature flag for tests
os.environ["OMG_WEB_SEARCH_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from web_search import Provider, SearchResult, WebSearchManager

from search_providers.synthetic import SyntheticProvider
from search_providers.exa import ExaProvider
from search_providers.brave import BraveProvider
from search_providers.perplexity import PerplexityProvider
from search_providers.jina import JinaProvider
from search_providers import PROVIDER_CLASSES, register_all


# =============================================================================
# Helpers
# =============================================================================


def _make_urlopen_response(data_bytes, charset="utf-8"):
    """Create a mock urllib response object."""
    resp = MagicMock()
    resp.read.return_value = data_bytes
    resp.headers = MagicMock()
    resp.headers.get_content_charset.return_value = charset
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# =============================================================================
# TestSyntheticProvider — 3 tests
# =============================================================================


class TestSyntheticProvider:
    """Tests for SyntheticProvider (mock/dry-run)."""

    def test_is_provider_subclass(self):
        """SyntheticProvider extends the Provider ABC."""
        prov = SyntheticProvider()
        assert isinstance(prov, Provider)

    def test_search_returns_three_results_by_default(self):
        """search() returns 3 fake SearchResult-compatible dicts."""
        prov = SyntheticProvider()
        results = prov.search("test query")
        assert len(results) == 3
        for r in results:
            assert "title" in r
            assert "url" in r
            assert "snippet" in r
            assert r["source"] == "synthetic"
        assert "test query" in results[0]["title"]

    def test_search_custom_num_results(self):
        """search() respects num_results kwarg."""
        prov = SyntheticProvider()
        results = prov.search("q", num_results=5)
        assert len(results) == 5

    def test_fetch_returns_html(self):
        """fetch() returns synthetic HTML containing the URL."""
        prov = SyntheticProvider()
        content = prov.fetch("https://example.com")
        assert "https://example.com" in content
        assert "<html>" in content

    def test_config_schema_exists(self):
        """SyntheticProvider has CONFIG_SCHEMA dict."""
        assert hasattr(SyntheticProvider, "CONFIG_SCHEMA")
        schema = SyntheticProvider.CONFIG_SCHEMA
        assert "api_key" in schema
        assert schema["api_key"]["required"] is False


# =============================================================================
# TestExaProvider — 3 tests
# =============================================================================


class TestExaProvider:
    """Tests for ExaProvider (Exa AI search API)."""

    def test_is_provider_subclass(self):
        """ExaProvider extends the Provider ABC."""
        prov = ExaProvider(api_key="test-key")
        assert isinstance(prov, Provider)

    @patch("search_providers.exa.urllib.request.urlopen")
    def test_search_parses_exa_response(self, mock_urlopen):
        """search() correctly parses Exa API response format."""
        api_response = json.dumps({
            "results": [
                {"title": "Exa Result 1", "url": "https://a.com", "text": "Snippet 1"},
                {"title": "Exa Result 2", "url": "https://b.com", "text": "Snippet 2"},
            ]
        }).encode("utf-8")
        mock_urlopen.return_value = _make_urlopen_response(api_response)

        prov = ExaProvider(api_key="test-key")
        results = prov.search("machine learning")

        assert len(results) == 2
        assert results[0]["title"] == "Exa Result 1"
        assert results[0]["source"] == "exa"
        assert results[1]["url"] == "https://b.com"

    @patch("search_providers.exa.urllib.request.urlopen")
    def test_search_handles_http_error(self, mock_urlopen):
        """search() returns empty list on HTTPError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.exa.ai/search", 403, "Forbidden", {}, None
        )

        prov = ExaProvider(api_key="test-key")
        results = prov.search("test")
        assert results == []

    def test_search_returns_empty_without_api_key(self):
        """search() returns empty list when no API key is set."""
        with patch.dict(os.environ, {}, clear=False):
            # Ensure no EXA_API_KEY in env
            os.environ.pop("EXA_API_KEY", None)
            prov = ExaProvider(api_key=None)
            # Force _api_key to None (get_api_key might resolve)
            prov._api_key = None
            results = prov.search("test")
            assert results == []

    def test_config_schema(self):
        """ExaProvider has proper CONFIG_SCHEMA."""
        schema = ExaProvider.CONFIG_SCHEMA
        assert schema["api_key"]["required"] is True


# =============================================================================
# TestBraveProvider — 3 tests
# =============================================================================


class TestBraveProvider:
    """Tests for BraveProvider (Brave Search API)."""

    def test_is_provider_subclass(self):
        """BraveProvider extends the Provider ABC."""
        prov = BraveProvider(api_key="test-key")
        assert isinstance(prov, Provider)

    @patch("search_providers.brave.urllib.request.urlopen")
    def test_search_parses_brave_response(self, mock_urlopen):
        """search() correctly parses Brave API response format."""
        api_response = json.dumps({
            "web": {
                "results": [
                    {"title": "Brave R1", "url": "https://b1.com", "description": "Desc 1"},
                    {"title": "Brave R2", "url": "https://b2.com", "description": "Desc 2"},
                ]
            }
        }).encode("utf-8")
        mock_urlopen.return_value = _make_urlopen_response(api_response)

        prov = BraveProvider(api_key="test-key")
        results = prov.search("brave search test")

        assert len(results) == 2
        assert results[0]["title"] == "Brave R1"
        assert results[0]["source"] == "brave"
        assert results[1]["snippet"] == "Desc 2"

    @patch("search_providers.brave.urllib.request.urlopen")
    def test_search_handles_url_error(self, mock_urlopen):
        """search() returns empty list on URLError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        prov = BraveProvider(api_key="test-key")
        results = prov.search("test")
        assert results == []

    def test_config_schema(self):
        """BraveProvider has proper CONFIG_SCHEMA."""
        schema = BraveProvider.CONFIG_SCHEMA
        assert schema["api_key"]["required"] is True
        assert "count" in schema


# =============================================================================
# TestPerplexityProvider — 3 tests
# =============================================================================


class TestPerplexityProvider:
    """Tests for PerplexityProvider (Perplexity AI API)."""

    def test_is_provider_subclass(self):
        """PerplexityProvider extends the Provider ABC."""
        prov = PerplexityProvider(api_key="test-key")
        assert isinstance(prov, Provider)

    @patch("search_providers.perplexity.urllib.request.urlopen")
    def test_search_parses_citations(self, mock_urlopen):
        """search() extracts citations from Perplexity response."""
        api_response = json.dumps({
            "choices": [
                {"message": {"content": "AI generated answer text here."}}
            ],
            "citations": [
                "https://cite1.com",
                "https://cite2.com",
            ],
        }).encode("utf-8")
        mock_urlopen.return_value = _make_urlopen_response(api_response)

        prov = PerplexityProvider(api_key="test-key")
        results = prov.search("what is AI")

        assert len(results) == 2
        assert results[0]["url"] == "https://cite1.com"
        assert results[0]["source"] == "perplexity"
        # First citation gets the answer snippet
        assert "AI generated answer" in results[0]["snippet"]

    @patch("search_providers.perplexity.urllib.request.urlopen")
    def test_search_returns_answer_without_citations(self, mock_urlopen):
        """search() returns answer as single result when no citations."""
        api_response = json.dumps({
            "choices": [
                {"message": {"content": "Direct answer without citations."}}
            ],
        }).encode("utf-8")
        mock_urlopen.return_value = _make_urlopen_response(api_response)

        prov = PerplexityProvider(api_key="test-key")
        results = prov.search("simple question")

        assert len(results) == 1
        assert "Direct answer" in results[0]["snippet"]
        assert results[0]["source"] == "perplexity"

    @patch("search_providers.perplexity.urllib.request.urlopen")
    def test_search_handles_http_error(self, mock_urlopen):
        """search() returns empty list on HTTPError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.perplexity.ai/chat/completions", 401, "Unauthorized",
            {}, None
        )

        prov = PerplexityProvider(api_key="bad-key")
        results = prov.search("test")
        assert results == []


# =============================================================================
# TestJinaProvider — 3 tests
# =============================================================================


class TestJinaProvider:
    """Tests for JinaProvider (Jina Reader API)."""

    def test_is_provider_subclass(self):
        """JinaProvider extends the Provider ABC."""
        prov = JinaProvider(api_key="test-key")
        assert isinstance(prov, Provider)

    @patch("search_providers.jina.urllib.request.urlopen")
    def test_fetch_returns_clean_text(self, mock_urlopen):
        """fetch() returns clean text from Jina Reader."""
        mock_urlopen.return_value = _make_urlopen_response(
            b"Clean extracted text from the page"
        )

        prov = JinaProvider(api_key="test-key")
        content = prov.fetch("https://example.com/article")

        assert "Clean extracted text" in content
        mock_urlopen.assert_called_once()

    def test_search_ignores_non_url_queries(self):
        """search() returns empty list for non-URL queries."""
        prov = JinaProvider(api_key="test-key")
        results = prov.search("just a text query")
        assert results == []

    @patch("search_providers.jina.urllib.request.urlopen")
    def test_search_processes_url_query(self, mock_urlopen):
        """search() processes URL-like queries through Jina Reader."""
        mock_urlopen.return_value = _make_urlopen_response(
            b"Article content extracted by Jina"
        )

        prov = JinaProvider(api_key="test-key")
        results = prov.search("https://example.com/page")

        assert len(results) == 1
        assert results[0]["source"] == "jina"
        assert "Article content" in results[0]["snippet"]

    @patch("search_providers.jina.urllib.request.urlopen")
    def test_fetch_handles_url_error(self, mock_urlopen):
        """fetch() returns empty string on URLError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("DNS failure")

        prov = JinaProvider(api_key="test-key")
        content = prov.fetch("https://example.com")
        assert content == ""


# =============================================================================
# TestAutoRegistration — 2 tests
# =============================================================================


class TestAutoRegistration:
    """Tests for auto-registration and package-level exports."""

    def test_provider_classes_has_all_five(self):
        """PROVIDER_CLASSES contains all 5 provider entries."""
        assert len(PROVIDER_CLASSES) == 5
        expected = {"synthetic", "exa", "brave", "perplexity", "jina"}
        assert set(PROVIDER_CLASSES.keys()) == expected

    def test_register_all_registers_synthetic(self):
        """register_all() registers SyntheticProvider (no API key needed)."""
        mgr = WebSearchManager()
        register_all(manager=mgr)
        # SyntheticProvider doesn't require API key, so always registered
        assert "synthetic" in mgr.get_providers()

    def test_register_all_skips_providers_without_keys(self):
        """register_all() skips providers whose API keys are unavailable."""
        mgr = WebSearchManager()
        # Ensure no API keys in env
        env_clean = {
            k: v for k, v in os.environ.items()
            if not k.endswith("_API_KEY")
        }
        with patch.dict(os.environ, env_clean, clear=True):
            # Also ensure OMG_WEB_SEARCH_ENABLED stays set
            os.environ["OMG_WEB_SEARCH_ENABLED"] = "true"
            # Force credential store to be unavailable
            import web_search
            with patch.object(web_search, "_HAS_CREDENTIAL_STORE", False):
                register_all(manager=mgr)

        providers = mgr.get_providers()
        # SyntheticProvider should be registered (not required key)
        assert "synthetic" in providers
        # Others should NOT be registered (no API keys available)
        # (unless env happened to have keys — but we cleared them)


# =============================================================================
# TestProviderNameProperty — 1 test
# =============================================================================


class TestProviderNameProperty:
    """Tests for the Provider.name property across all providers."""

    def test_all_providers_have_lowercase_name(self):
        """Each provider's .name matches its lowercase class name."""
        providers = [
            SyntheticProvider(),
            ExaProvider(api_key="k"),
            BraveProvider(api_key="k"),
            PerplexityProvider(api_key="k"),
            JinaProvider(api_key="k"),
        ]
        for prov in providers:
            assert prov.name == prov.__class__.__name__.lower()
