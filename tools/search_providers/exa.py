#!/usr/bin/env python3
"""
Exa Search Provider for OAL

Uses the Exa AI search API (https://api.exa.ai/search) for semantic web search.
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


class ExaProvider(Provider):
    """Search provider using the Exa AI search API.

    Endpoint: https://api.exa.ai/search
    Requires an API key (EXA_API_KEY env var or credential store).
    """

    CONFIG_SCHEMA: Dict[str, Any] = {
        "api_key": {"type": "str", "required": True},
        "num_results": {"type": "int", "required": False, "default": 10},
        "use_autoprompt": {"type": "bool", "required": False, "default": True},
    }

    API_URL = "https://api.exa.ai/search"

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize ExaProvider.

        Args:
            api_key: Exa API key. If None, resolves via get_api_key('exa').
        """
        self._api_key = api_key or get_api_key("exa")

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        """Search using the Exa AI API.

        Args:
            query: The search query string.
            **kwargs: Optional 'num_results' (default 10), 'use_autoprompt'.

        Returns:
            A list of result dicts, or empty list on error.
        """
        if not self._api_key:
            return []

        num_results = kwargs.get("num_results", 10)
        use_autoprompt = kwargs.get("use_autoprompt", True)

        payload = json.dumps({
            "query": query,
            "numResults": num_results,
            "useAutoprompt": use_autoprompt,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "User-Agent": "OAL-WebSearch/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError):
            return []
        except Exception:
            return []

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("text", item.get("snippet", "")),
                "source": "exa",
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
