#!/usr/bin/env python3
"""
Web Search Provider Abstraction for OMG

Clean provider interface for web search with credential integration.
Providers register via the abstract base class; WebSearchManager dispatches
search/fetch calls to the active provider.

Feature flag: OMG_WEB_SEARCH_ENABLED (default: False)
"""

import abc
import importlib
import time
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# --- Lazy imports for hooks/_common.py ---

_get_feature_flag = None
_atomic_json_write = None


def _ensure_imports():
    """Lazy import feature flag and atomic write from hooks/_common.py."""
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


# --- Lazy import for credential_store (OPTIONAL) ---

_credential_store = None
_has_credential_store: Optional[bool] = None
# Backward-compat test seam (patched in existing tests).
_HAS_CREDENTIAL_STORE = None


def _resolve_project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _mark_external_ingress(*, source_ref: str, content: Any) -> None:
    try:
        from runtime.untrusted_content import TrustTier, mark_untrusted_content
    except Exception:
        return

    payload = content
    if not isinstance(payload, str):
        payload = json.dumps(payload, sort_keys=True, ensure_ascii=True)

    try:
        mark_untrusted_content(
            _resolve_project_dir(),
            source_type="web",
            source_ref=source_ref,
            content=payload,
            tier=TrustTier.RESEARCH,
        )
    except Exception:
        return


def _check_credential_store() -> bool:
    """Check if credential_store is available (cached after first check)."""
    global _has_credential_store, _credential_store
    override = globals().get("_HAS_CREDENTIAL_STORE")
    if override is not None:
        return bool(override)

    if _has_credential_store is None:
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            hooks_dir = os.path.join(repo_root, "hooks")
            if hooks_dir not in sys.path:
                sys.path.insert(0, hooks_dir)
            _cs = importlib.import_module("credential_store")
            _credential_store = _cs
            _has_credential_store = True
        except ImportError:
            _has_credential_store = False
    return bool(_has_credential_store)


# --- Feature flag ---

def _is_enabled() -> bool:
    """Check if Web Search feature is enabled."""
    # Fast path: check env var directly
    env_val = os.environ.get("OMG_WEB_SEARCH_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    # Fallback to hooks/_common.get_feature_flag
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("WEB_SEARCH", default=False)
    return False


# =============================================================================
# Data Types
# =============================================================================


@dataclass
class SearchResult:
    """A single search result from a web search provider.

    Attributes:
        title: The title of the search result.
        url: The URL of the search result.
        snippet: A text snippet or summary from the result.
        source: The provider name that produced this result.
    """
    title: str
    url: str
    snippet: str
    source: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "SearchResult":
        """Create a SearchResult from a dictionary.

        Accepts dicts with at least 'title', 'url', 'snippet', 'source' keys.
        Missing keys default to empty string.
        """
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            snippet=data.get("snippet", ""),
            source=data.get("source", ""),
        )


# =============================================================================
# Abstract Provider Base Class
# =============================================================================


class Provider(abc.ABC):
    """Abstract base class for web search providers.

    Subclasses must implement `search()` and `fetch()`.
    """

    @abc.abstractmethod
    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        """Search the web for the given query.

        Args:
            query: The search query string.
            **kwargs: Provider-specific options (e.g., num_results, language).

        Returns:
            A list of dicts, each with at least 'title', 'url', 'snippet' keys.
        """
        ...

    @abc.abstractmethod
    def fetch(self, url: str) -> str:
        """Fetch the content of a URL and return it as text.

        Args:
            url: The URL to fetch.

        Returns:
            The page content as a string.
        """
        ...

    @property
    def name(self) -> str:
        """Provider name (defaults to class name in lowercase)."""
        return self.__class__.__name__.lower()


# =============================================================================
# Credential Lookup
# =============================================================================


def get_api_key(provider_name: str) -> Optional[str]:
    """Get the API key for a provider.

    Resolution order:
        1. credential_store.get_active_key(provider_name) if available
        2. Environment variable {PROVIDER_NAME}_API_KEY

    Args:
        provider_name: The name of the provider (e.g., 'exa', 'serper').

    Returns:
        The API key string, or None if not found.
    """
    # Try credential store first
    if _check_credential_store() and _credential_store is not None:
        try:
            key = _credential_store.get_active_key(provider_name)
            if key:
                return key
        except (RuntimeError, ValueError, OSError):
            pass  # Fall through to env var

    # Fallback to environment variable
    env_key = f"{provider_name.upper()}_API_KEY"
    return os.environ.get(env_key)


# =============================================================================
# Web Search Manager
# =============================================================================


class WebSearchManager:
    """Central manager for web search operations.

    Manages registered providers and dispatches search/fetch calls.
    All public methods return early with error/empty if the feature flag
    is disabled.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, Provider] = {}
        self._default_provider: Optional[str] = None

    def register_provider(self, name: str, provider: Provider) -> None:
        """Register a search provider.

        Args:
            name: A unique name for the provider (e.g., 'exa', 'serper').
            provider: An instance of a Provider subclass.
        """
        self._providers[name] = provider
        # First registered provider becomes default
        if self._default_provider is None:
            self._default_provider = name

    def unregister_provider(self, name: str) -> bool:
        """Remove a registered provider.

        Args:
            name: The provider name to remove.

        Returns:
            True if removed, False if not found.
        """
        if name in self._providers:
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = (
                    next(iter(self._providers)) if self._providers else None
                )
            return True
        return False

    def get_providers(self) -> List[str]:
        """Return a list of registered provider names.

        Returns:
            List of provider name strings.
        """
        return list(self._providers.keys())

    def search(
        self,
        query: str,
        provider: Optional[str] = None,
        use_selector: bool = False,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> List[SearchResult]:
        """Search using a registered provider.

        Args:
            query: The search query string.
            provider: Provider name to use. If None, uses the default provider
                (or ProviderSelector if use_selector=True).
            use_selector: If True, use ProviderSelector for intelligent
                provider selection with fallback and rate-limit awareness.
            dry_run: If True (with use_selector), prefer synthetic provider.
            **kwargs: Additional arguments passed to the provider's search().

        Returns:
            A list of SearchResult objects. Empty list if feature disabled,
            no providers registered, or provider not found.
        """
        if not _is_enabled():
            return []

        if use_selector:
            provider_name = provider_selector.select_provider(
                query=query,
                preferred=provider,
                manager=self,
                dry_run=dry_run,
            )
        else:
            provider_name = provider or self._default_provider

        if provider_name is None or provider_name not in self._providers:
            return []

        prov = self._providers[provider_name]
        try:
            raw_results = prov.search(query, **kwargs)
        except Exception:
            return []

        results = []
        for item in raw_results:
            item.setdefault("source", provider_name)
            results.append(SearchResult.from_dict(item))

        _mark_external_ingress(
            source_ref=f"search:{provider_name}",
            content={
                "query": query,
                "provider": provider_name,
                "results": [result.to_dict() for result in results],
            },
        )
        return results

    def fetch(
        self,
        url: str,
        provider: Optional[str] = None,
    ) -> str:
        """Fetch URL content using a registered provider.

        Args:
            url: The URL to fetch.
            provider: Provider name to use. If None, uses default provider.
                If no provider registered, uses stdlib urllib as fallback.

        Returns:
            The fetched content as a string, or empty string on failure/disabled.
        """
        if not _is_enabled():
            return ""

        provider_name = provider or self._default_provider
        if provider_name and provider_name in self._providers:
            try:
                content = self._providers[provider_name].fetch(url)
            except Exception:
                return ""
            _mark_external_ingress(
                source_ref=f"fetch:{provider_name}:{url}",
                content={
                    "url": url,
                    "provider": provider_name,
                    "content": content,
                },
            )
            return content

        # Fallback: use stdlib urllib if no provider available
        content = _stdlib_fetch(url)
        _mark_external_ingress(
            source_ref=f"fetch:stdlib:{url}",
            content={
                "url": url,
                "provider": "stdlib",
                "content": content,
            },
        )
        return content


# =============================================================================
# Stdlib URL Fetch (fallback)
# =============================================================================


def _stdlib_fetch(url: str, timeout: int = 15) -> str:
    """Fetch URL content using stdlib urllib.request.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        The page content as text, or empty string on failure.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OMG-WebSearch/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            encoding = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(encoding, errors="replace")
    except Exception:
        return ""

# =============================================================================
# Provider Selection Logic
# =============================================================================


# Module-level rate limit state: provider_name -> reset_timestamp
_rate_limits: Dict[str, float] = {}

# Default fallback chain order
DEFAULT_FALLBACK_CHAIN = ["exa", "brave", "perplexity", "jina", "synthetic"]


class ProviderSelector:
    """Intelligent provider selection with fallback chains and rate-limit tracking.

    Selection algorithm:
        1. If dry-run mode, prefer 'synthetic'
        2. If `preferred` argument given, use it (if not rate-limited)
        3. If user preference is set, use it (if not rate-limited)
        4. Iterate fallback chain, pick first not rate-limited + registered
        5. Return None if all exhausted
    """

    def __init__(self) -> None:
        self._preference_path: Optional[str] = None

    def _get_preference_path(self) -> str:
        """Get the path to the preference file."""
        if self._preference_path is None:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._preference_path = os.path.join(
                repo_root, ".omg", "state", "search_preference.json"
            )
        return self._preference_path

    def select_provider(
        self,
        query: str,
        preferred: Optional[str] = None,
        manager: Optional["WebSearchManager"] = None,
        dry_run: bool = False,
    ) -> Optional[str]:
        """Pick the best available provider for a query.

        Args:
            query: The search query (reserved for future query-type routing).
            preferred: Explicit provider preference for this call.
            manager: WebSearchManager to check registered providers against.
            dry_run: If True, prefer 'synthetic' provider.

        Returns:
            Provider name string, or None if no provider available.
        """
        registered = manager.get_providers() if manager else []

        # Step 0: dry-run mode prefers synthetic
        if dry_run and "synthetic" in registered and not self.is_rate_limited("synthetic"):
            return "synthetic"

        # Step 1: explicit preferred argument
        if preferred and preferred in registered and not self.is_rate_limited(preferred):
            return preferred

        # Step 2: user preference from persisted state
        user_pref = self.get_preference()
        if user_pref and user_pref in registered and not self.is_rate_limited(user_pref):
            return user_pref

        # Step 3: iterate fallback chain
        for provider_name in DEFAULT_FALLBACK_CHAIN:
            if provider_name in registered and not self.is_rate_limited(provider_name):
                return provider_name

        # Step 4: try any remaining registered provider not in fallback chain
        for provider_name in registered:
            if not self.is_rate_limited(provider_name):
                return provider_name

        return None

    def record_rate_limit(
        self, provider_name: str, reset_at: Optional[float] = None
    ) -> None:
        """Mark a provider as rate-limited.

        Args:
            provider_name: The provider to mark.
            reset_at: Unix timestamp when the rate limit resets.
                      Defaults to time.time() + 60 (1 minute).
        """
        if reset_at is None:
            reset_at = time.time() + 60
        _rate_limits[provider_name] = reset_at

    def is_rate_limited(self, provider_name: str) -> bool:
        """Check if a provider is currently rate-limited.

        Automatically clears expired rate limits.

        Args:
            provider_name: The provider to check.

        Returns:
            True if currently rate-limited, False otherwise.
        """
        if provider_name not in _rate_limits:
            return False
        if time.time() > _rate_limits[provider_name]:
            # Rate limit expired — clean up
            del _rate_limits[provider_name]
            return False
        return True

    def get_fallback_chain(self, primary_provider: str) -> List[str]:
        """Return ordered fallback list starting after the primary provider.

        Args:
            primary_provider: The provider to build fallback chain from.

        Returns:
            List of provider names in fallback order (excluding primary).
        """
        chain = list(DEFAULT_FALLBACK_CHAIN)
        if primary_provider in chain:
            idx = chain.index(primary_provider)
            # Everything after primary, then wrap around before it
            chain = chain[idx + 1:] + chain[:idx]
        return chain

    def set_preference(self, provider_name: str) -> None:
        """Persist user preferred provider to .omg/state/search_preference.json.

        Args:
            provider_name: The provider name to set as default.
        """
        import datetime

        _ensure_imports()
        data = {
            "provider": provider_name,
            "set_at": datetime.datetime.now().isoformat(),
        }
        path = self._get_preference_path()
        if _atomic_json_write is not None:
            _atomic_json_write(path, data)
        else:
            # Fallback: direct write
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    def get_preference(self) -> Optional[str]:
        """Read user preferred provider from persisted state.

        Returns:
            Provider name string, or None if no preference set.
        """
        path = self._get_preference_path()
        try:
            with open(path) as f:
                data = json.load(f)
            return data.get("provider")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None


# Module-level singleton
provider_selector = ProviderSelector()


# =============================================================================
# Module-Level Singleton Instance
# =============================================================================

manager = WebSearchManager()

# Auto-register bundled providers so CLI and hooks work out of the box.
# - synthetic always registers (no API key required)
# - api-key providers register only when credentials are available
try:
    _providers_mod = importlib.import_module("search_providers")
    _providers_mod.register_all(manager=manager)
except Exception:
    # Keep module import non-fatal if provider modules are unavailable.
    pass

# =============================================================================
# CLI Interface
# =============================================================================


def _cli_main():
    """CLI entry point for web_search.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG Web Search Tool — provider-based web search abstraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", help="Search query string")
    parser.add_argument("--provider", help="Provider name to use")
    parser.add_argument("--fetch", dest="fetch_url", help="Fetch URL content")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be searched without making real API calls",
    )
    parser.add_argument(
        "--list-providers", action="store_true",
        help="List registered providers",
    )

    args = parser.parse_args()

    # Check feature flag for most operations
    enabled = _is_enabled()

    if args.list_providers:
        providers = manager.get_providers()
        print(json.dumps({"providers": providers, "enabled": enabled}))
        return

    if args.dry_run and args.query:
        print(json.dumps({
            "dry_run": True,
            "query": args.query,
            "provider": args.provider or manager._default_provider or "(none)",
            "enabled": enabled,
            "registered_providers": manager.get_providers(),
            "would_search": enabled and len(manager.get_providers()) > 0,
        }, indent=2))
        return

    if not enabled:
        print(json.dumps({"error": "Web search is disabled (OMG_WEB_SEARCH_ENABLED=false)"}))
        sys.exit(1)

    if args.fetch_url:
        content = manager.fetch(args.fetch_url, provider=args.provider)
        print(json.dumps({
            "url": args.fetch_url,
            "content_length": len(content),
            "content_preview": content[:500] if content else "",
        }, indent=2))
        return

    if args.query:
        results = manager.search(args.query, provider=args.provider)
        output = [r.to_dict() for r in results]
        print(json.dumps({"results": output, "count": len(output)}, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
