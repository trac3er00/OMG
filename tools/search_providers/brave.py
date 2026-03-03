#!/usr/bin/env python3
"""
Brave Search Provider for OAL

Uses the Brave Search API (https://api.search.brave.com/res/v1/web/search).
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from web_search import Provider, SearchResult, get_api_key


class BraveProvider(Provider):
    """Search provider using the Brave Search API.

    Endpoint: https://api.search.brave.com/res/v1/web/search
    Requires an API key (BRAVE_API_KEY env var or credential store).
    """

    CONFIG_SCHEMA: Dict[str, Any] = {
        "api_key": {"type": "str", "required": True},
        "count": {"type": "int", "required": False, "default": 10},
        "country": {"type": "str", "required": False, "default": ""},
    }

    API_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize BraveProvider.

        Args:
            api_key: Brave API key. If None, resolves via get_api_key('brave').
        """
        self._api_key = api_key or get_api_key("brave")

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        """Search using the Brave Search API.

        Args:
            query: The search query string.
            **kwargs: Optional 'count' (default 10), 'country'.

        Returns:
            A list of result dicts, or empty list on error.
        """
        if not self._api_key:
            return []

        count = kwargs.get("count", 10)
        params = {"q": query, "count": str(count)}
        country = kwargs.get("country", "")
        if country:
            params["country"] = country

        url = f"{self.API_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self._api_key,
                "User-Agent": "OAL-WebSearch/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError):
            return []
        except Exception:
            return []

        results = []
        web_results = data.get("web", {}).get("results", [])
        for item in web_results:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "source": "brave",
            })
        return results

    def fetch(self, url: str) -> str:
        """Fetch URL content using stdlib urllib.

        Args:
            url: The URL to fetch.

        Returns:
            Page content as string, or empty string on error.
        """
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "OAL-WebSearch/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                encoding = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(encoding, errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError):
            return ""
        except Exception:
            return ""
