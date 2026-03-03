#!/usr/bin/env python3
"""
Jina Reader Provider for OAL

Uses the Jina Reader API (https://r.jina.ai/) for URL-based content extraction.
Jina Reader converts web pages to clean, readable text — it is primarily a
fetch/reader tool rather than a traditional search engine.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from web_search import Provider, SearchResult, get_api_key


class JinaProvider(Provider):
    """Content extraction provider using Jina Reader API.

    Endpoint: https://r.jina.ai/{url}
    Optionally accepts an API key (JINA_API_KEY) for higher rate limits.
    Primary use is fetch() — search() builds a reader URL from the query.
    """

    CONFIG_SCHEMA: Dict[str, Any] = {
        "api_key": {"type": "str", "required": False},
        "return_format": {"type": "str", "required": False, "default": "text"},
    }

    BASE_URL = "https://r.jina.ai/"

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize JinaProvider.

        Args:
            api_key: Jina API key. Optional — Jina works without a key
                     but has lower rate limits.
        """
        self._api_key = api_key or get_api_key("jina")

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        """Search by treating the query as a URL to read via Jina.

        If the query looks like a URL, fetches it through Jina Reader.
        Otherwise, returns an empty list (Jina Reader is URL-based, not
        a search engine).

        Args:
            query: A URL string to read, or a search query (returns empty).
            **kwargs: Optional 'return_format' ('text' or 'markdown').

        Returns:
            A list with one result dict if query is a URL, else empty list.
        """
        # Jina Reader is URL-based — only process URLs
        if not query.startswith(("http://", "https://")):
            return []

        content = self.fetch(query)
        if not content:
            return []

        return [{
            "title": f"Jina Reader: {query[:80]}",
            "url": query,
            "snippet": content[:500],
            "source": "jina",
        }]

    def fetch(self, url: str) -> str:
        """Fetch and extract clean text from a URL using Jina Reader.

        Args:
            url: The URL to fetch and extract content from.

        Returns:
            Clean text content, or empty string on error.
        """
        reader_url = f"{self.BASE_URL}{url}"

        headers = {
            "Accept": "text/plain",
            "User-Agent": "OAL-WebSearch/1.0",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = urllib.request.Request(reader_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                encoding = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(encoding, errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError):
            return ""
        except Exception:
            return ""
