#!/usr/bin/env python3
"""
Synthetic Search Provider for OMG

Returns mock/fake results without making any API calls.
Useful for testing, dry-run mode, and offline development.
"""

import os
import sys
from typing import Any, Dict, List, Optional

# Ensure tools dir is on path for imports
_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from web_search import Provider, SearchResult


class SyntheticProvider(Provider):
    """Mock search provider that returns fake results without API calls.

    Designed for testing, dry-run mode, and offline development.
    Does not require any API key or network access.
    """

    CONFIG_SCHEMA: Dict[str, Any] = {
        "api_key": {"type": "str", "required": False},
        "num_results": {"type": "int", "required": False, "default": 3},
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize SyntheticProvider.

        Args:
            api_key: Ignored — synthetic provider needs no credentials.
        """
        self._api_key = api_key  # Accepted but unused

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        """Return synthetic search results for any query.

        Args:
            query: The search query string.
            **kwargs: Optional 'num_results' (default 3).

        Returns:
            A list of fake result dicts with title, url, snippet keys.
        """
        num_results = kwargs.get("num_results", 3)
        results = []
        for i in range(1, num_results + 1):
            results.append({
                "title": f"Synthetic Result {i} for: {query}",
                "url": f"https://synthetic.example.com/result/{i}",
                "snippet": f"This is a synthetic snippet #{i} for query '{query}'.",
                "source": "synthetic",
            })
        return results

    def fetch(self, url: str) -> str:
        """Return synthetic page content for any URL.

        Args:
            url: The URL to 'fetch'.

        Returns:
            A synthetic HTML string mentioning the URL.
        """
        return (
            f"<html><head><title>Synthetic Page</title></head>"
            f"<body><p>Synthetic content for {url}</p></body></html>"
        )
