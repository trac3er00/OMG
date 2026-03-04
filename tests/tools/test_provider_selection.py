#!/usr/bin/env python3
"""
Tests for ProviderSelector — intelligent provider selection with fallback
chains, rate-limit tracking, and user preference persistence.

Task 4.3: Provider Selection Logic
"""

import json
import os
import sys
import time
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# Enable feature flag for tests
os.environ["OMG_WEB_SEARCH_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

import web_search
from web_search import (
    DEFAULT_FALLBACK_CHAIN,
    Provider,
    ProviderSelector,
    SearchResult,
    WebSearchManager,
    _rate_limits,
    provider_selector,
)


# --- Concrete test provider ---


class StubProvider(Provider):
    """Minimal concrete provider for testing."""

    def __init__(self, name_override: str = ""):
        self._name_override = name_override

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        return [{"title": f"Result from {self.name}", "url": "https://example.com", "snippet": "stub"}]

    def fetch(self, url: str) -> str:
        return "stub content"

    @property
    def name(self) -> str:
        return self._name_override or super().name


# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_state():
    """Reset rate limits and manager before each test."""
    _rate_limits.clear()
    web_search.manager._providers.clear()
    web_search.manager._default_provider = None
    yield
    _rate_limits.clear()
    web_search.manager._providers.clear()
    web_search.manager._default_provider = None


@pytest.fixture
def selector():
    """Fresh ProviderSelector instance."""
    return ProviderSelector()


@pytest.fixture
def populated_manager():
    """Manager with exa, brave, and synthetic providers registered."""
    mgr = WebSearchManager()
    mgr.register_provider("exa", StubProvider("exa"))
    mgr.register_provider("brave", StubProvider("brave"))
    mgr.register_provider("synthetic", StubProvider("synthetic"))
    return mgr


# =============================================================================
# Test ProviderSelector.select_provider — core selection algorithm (5 tests)
# =============================================================================


class TestSelectProvider:
    """Tests for the select_provider() method."""

    def test_selects_first_available_from_fallback_chain(self, selector, populated_manager):
        """Picks first available provider from the fallback chain."""
        result = selector.select_provider("test query", manager=populated_manager)
        assert result == "exa"  # exa is first in DEFAULT_FALLBACK_CHAIN

    def test_honors_preferred_argument(self, selector, populated_manager):
        """Preferred argument overrides fallback chain."""
        result = selector.select_provider("test", preferred="brave", manager=populated_manager)
        assert result == "brave"

    def test_skips_rate_limited_preferred(self, selector, populated_manager):
        """Falls back when preferred provider is rate-limited."""
        selector.record_rate_limit("brave", reset_at=time.time() + 300)
        result = selector.select_provider("test", preferred="brave", manager=populated_manager)
        # Should skip brave and pick exa (first in fallback chain)
        assert result == "exa"

    def test_returns_none_when_all_exhausted(self, selector):
        """Returns None when no providers are available."""
        mgr = WebSearchManager()
        result = selector.select_provider("test", manager=mgr)
        assert result is None

    def test_prefers_synthetic_in_dry_run(self, selector, populated_manager):
        """Dry-run mode prefers synthetic provider."""
        result = selector.select_provider("test", manager=populated_manager, dry_run=True)
        assert result == "synthetic"

    def test_skips_unregistered_preferred(self, selector, populated_manager):
        """Falls back to chain when preferred is not registered."""
        result = selector.select_provider("test", preferred="nonexistent", manager=populated_manager)
        assert result == "exa"

    def test_all_rate_limited_returns_none(self, selector, populated_manager):
        """Returns None when every registered provider is rate-limited."""
        future = time.time() + 300
        selector.record_rate_limit("exa", reset_at=future)
        selector.record_rate_limit("brave", reset_at=future)
        selector.record_rate_limit("synthetic", reset_at=future)
        result = selector.select_provider("test", manager=populated_manager)
        assert result is None


# =============================================================================
# Test rate limit tracking (3 tests)
# =============================================================================


class TestRateLimiting:
    """Tests for rate limit recording and checking."""

    def test_record_and_check_rate_limit(self, selector):
        """Record a rate limit and verify it's detected."""
        selector.record_rate_limit("exa", reset_at=time.time() + 60)
        assert selector.is_rate_limited("exa") is True

    def test_rate_limit_expires(self, selector):
        """Rate limit is cleared after expiry time."""
        selector.record_rate_limit("exa", reset_at=time.time() - 1)  # Already expired
        assert selector.is_rate_limited("exa") is False

    def test_rate_limit_default_reset(self, selector):
        """Default reset time is ~60 seconds from now."""
        before = time.time() + 59
        selector.record_rate_limit("brave")
        after = time.time() + 61
        assert "brave" in _rate_limits
        assert before <= _rate_limits["brave"] <= after

    def test_unknown_provider_not_rate_limited(self, selector):
        """Unknown provider is not rate-limited."""
        assert selector.is_rate_limited("nonexistent") is False


# =============================================================================
# Test fallback chain (2 tests)
# =============================================================================


class TestFallbackChain:
    """Tests for get_fallback_chain()."""

    def test_default_fallback_chain_order(self):
        """DEFAULT_FALLBACK_CHAIN has expected order."""
        assert DEFAULT_FALLBACK_CHAIN == ["exa", "brave", "perplexity", "jina", "synthetic"]

    def test_get_fallback_chain_excludes_primary(self, selector):
        """Fallback chain excludes the primary provider."""
        chain = selector.get_fallback_chain("exa")
        assert "exa" not in chain
        assert chain[0] == "brave"

    def test_get_fallback_chain_wraps_around(self, selector):
        """Fallback chain wraps around when primary is in the middle."""
        chain = selector.get_fallback_chain("perplexity")
        # After perplexity: jina, synthetic, then before: exa, brave
        assert chain == ["jina", "synthetic", "exa", "brave"]

    def test_get_fallback_chain_unknown_primary(self, selector):
        """Fallback chain returns full list for unknown primary."""
        chain = selector.get_fallback_chain("unknown_provider")
        assert chain == DEFAULT_FALLBACK_CHAIN


# =============================================================================
# Test preference persistence (3 tests)
# =============================================================================


class TestPreferencePersistence:
    """Tests for set_preference() and get_preference()."""

    def test_set_and_get_preference(self, selector, tmp_path):
        """Set and read back a user preference."""
        pref_path = str(tmp_path / "search_preference.json")
        selector._preference_path = pref_path
        selector.set_preference("brave")
        assert selector.get_preference() == "brave"

    def test_get_preference_returns_none_when_no_file(self, selector, tmp_path):
        """Returns None when no preference file exists."""
        pref_path = str(tmp_path / "nonexistent" / "search_preference.json")
        selector._preference_path = pref_path
        assert selector.get_preference() is None

    def test_preference_file_structure(self, selector, tmp_path):
        """Preference file contains provider and set_at fields."""
        pref_path = str(tmp_path / "search_preference.json")
        selector._preference_path = pref_path
        selector.set_preference("exa")
        with open(pref_path) as f:
            data = json.load(f)
        assert data["provider"] == "exa"
        assert "set_at" in data

    def test_preference_used_in_selection(self, selector, populated_manager, tmp_path):
        """User preference is used during provider selection."""
        pref_path = str(tmp_path / "search_preference.json")
        selector._preference_path = pref_path
        selector.set_preference("brave")
        result = selector.select_provider("test", manager=populated_manager)
        assert result == "brave"


# =============================================================================
# Test WebSearchManager integration with selector (2 tests)
# =============================================================================


class TestManagerSelectorIntegration:
    """Tests for WebSearchManager.search() with use_selector=True."""

    def test_search_with_selector(self):
        """search(use_selector=True) uses ProviderSelector."""
        mgr = WebSearchManager()
        mgr.register_provider("exa", StubProvider("exa"))
        mgr.register_provider("synthetic", StubProvider("synthetic"))
        results = mgr.search("test query", use_selector=True)
        assert len(results) > 0
        assert results[0].source == "exa"

    def test_search_with_selector_dry_run(self):
        """search(use_selector=True, dry_run=True) prefers synthetic."""
        mgr = WebSearchManager()
        mgr.register_provider("exa", StubProvider("exa"))
        mgr.register_provider("synthetic", StubProvider("synthetic"))
        results = mgr.search("test query", use_selector=True, dry_run=True)
        assert len(results) > 0
        assert results[0].source == "synthetic"

    def test_search_without_selector_unchanged(self):
        """search() without use_selector still works as before."""
        mgr = WebSearchManager()
        mgr.register_provider("mock", StubProvider("mock"))
        results = mgr.search("test query")
        assert len(results) == 1
        assert results[0].source == "mock"
