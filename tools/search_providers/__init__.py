#!/usr/bin/env python3
"""
OAL Search Providers Package

Auto-registers all bundled providers with the module-level WebSearchManager
from tools.web_search when this package is imported.

Providers:
    - SyntheticProvider: Mock results for testing/dry-run (no API key needed)
    - ExaProvider: Exa AI semantic search
    - BraveProvider: Brave Search API
    - PerplexityProvider: Perplexity AI chat completions
    - JinaProvider: Jina Reader URL-based content extraction
"""

import os
import sys

# Ensure tools dir is on path
_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from search_providers.synthetic import SyntheticProvider
from search_providers.exa import ExaProvider
from search_providers.brave import BraveProvider
from search_providers.perplexity import PerplexityProvider
from search_providers.jina import JinaProvider

__all__ = [
    "SyntheticProvider",
    "ExaProvider",
    "BraveProvider",
    "PerplexityProvider",
    "JinaProvider",
    "register_all",
]

# Provider registry: name -> class mapping
PROVIDER_CLASSES = {
    "synthetic": SyntheticProvider,
    "exa": ExaProvider,
    "brave": BraveProvider,
    "perplexity": PerplexityProvider,
    "jina": JinaProvider,
}


def register_all(manager=None):
    """Register all bundled providers with a WebSearchManager.

    If no manager is given, uses the module-level singleton from web_search.

    Only instantiates providers that either:
      - Don't require an API key (SyntheticProvider)
      - Have a resolvable API key (env var or credential store)

    Args:
        manager: A WebSearchManager instance. Defaults to web_search.manager.
    """
    if manager is None:
        from web_search import manager as _mgr
        manager = _mgr

    for name, cls in PROVIDER_CLASSES.items():
        schema = getattr(cls, "CONFIG_SCHEMA", {})
        api_key_required = schema.get("api_key", {}).get("required", False)

        if not api_key_required:
            # No API key required — always register (e.g., SyntheticProvider)
            manager.register_provider(name, cls())
        else:
            # Only register if API key is available
            from web_search import get_api_key
            key = get_api_key(name)
            if key:
                manager.register_provider(name, cls(api_key=key))
