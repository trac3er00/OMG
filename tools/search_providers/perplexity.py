#!/usr/bin/env python3
"""
Perplexity Search Provider for OAL

Uses the Perplexity AI chat completions API
(https://api.perplexity.ai/chat/completions) for AI-powered web search.
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


class PerplexityProvider(Provider):
    """Search provider using the Perplexity AI API.

    Endpoint: https://api.perplexity.ai/chat/completions
    Requires an API key (PERPLEXITY_API_KEY env var or credential store).
    Uses the sonar model for online search-augmented responses.
    """

    CONFIG_SCHEMA: Dict[str, Any] = {
        "api_key": {"type": "str", "required": True},
        "model": {"type": "str", "required": False, "default": "sonar"},
    }

    API_URL = "https://api.perplexity.ai/chat/completions"

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize PerplexityProvider.

        Args:
            api_key: Perplexity API key. If None, resolves via
                     get_api_key('perplexity').
        """
        self._api_key = api_key or get_api_key("perplexity")

    def search(self, query: str, **kwargs: Any) -> List[Dict[str, str]]:
        """Search using the Perplexity AI API.

        Sends the query as a chat message and parses citations from the
        response into search result format.

        Args:
            query: The search query string.
            **kwargs: Optional 'model' (default 'sonar').

        Returns:
            A list of result dicts, or empty list on error.
        """
        if not self._api_key:
            return []

        model = kwargs.get("model", "sonar")

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "user", "content": query},
            ],
        }).encode("utf-8")

        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "User-Agent": "OAL-WebSearch/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError):
            return []
        except Exception:
            return []

        results = []
        # Extract answer text
        answer = ""
        choices = data.get("choices", [])
        if choices:
            answer = choices[0].get("message", {}).get("content", "")

        # Extract citations if available
        citations = data.get("citations", [])
        if citations:
            for i, url in enumerate(citations):
                results.append({
                    "title": f"Citation {i + 1}",
                    "url": url if isinstance(url, str) else str(url),
                    "snippet": answer[:200] if i == 0 else "",
                    "source": "perplexity",
                })
        elif answer:
            # No citations — return answer as a single result
            results.append({
                "title": f"Perplexity answer for: {query[:80]}",
                "url": "",
                "snippet": answer[:500],
                "source": "perplexity",
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
