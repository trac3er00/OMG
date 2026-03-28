"""OMG Natives — html: HTML→Markdown and HTML→text conversion.

Pure-Python fallback for HTML processing.
Uses ``re`` only — avoids importing stdlib ``html`` to prevent circular
import issues (this file is named ``html.py`` which shadows the stdlib).

Feature flag: ``OMG_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from omg_natives._bindings import bind_function


_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal HTML entity unescaping (avoids importing stdlib html module)
# ---------------------------------------------------------------------------

_ENTITIES: Dict[str, str] = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&nbsp;": " ",
}

_NUMERIC_ENTITY_RE = re.compile(r"&#x([0-9a-fA-F]+);|&#(\d+);")


def _unescape(text: str) -> str:
    """Minimal HTML entity unescaping."""
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)

    def _replace_numeric(m: re.Match) -> str:
        hex_val, dec_val = m.group(1), m.group(2)
        try:
            if hex_val:
                return chr(int(hex_val, 16))
            if dec_val:
                return chr(int(dec_val))
        except (ValueError, OverflowError) as exc:
            _logger.debug("Failed to decode numeric HTML entity '%s': %s", m.group(0), exc, exc_info=True)
        return m.group(0)

    return _NUMERIC_ENTITY_RE.sub(_replace_numeric, text)


# ---------------------------------------------------------------------------
# Regex-based HTML→Markdown converter (avoids stdlib html.parser)
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<(/?)(\w+)([^>]*)(/?)>", re.DOTALL)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*["\']([^"\']*)["\']')


def _html_to_markdown(content: str) -> str:
    """Convert basic HTML to Markdown using regex."""
    parts: List[str] = []
    last_end = 0
    pending_href: Optional[str] = None

    for m in _TAG_RE.finditer(content):
        text_before = content[last_end:m.start()]
        if text_before:
            parts.append(text_before)
        last_end = m.end()

        is_closing = m.group(1) == "/"
        tag = m.group(2).lower()
        attrs_str = m.group(3)

        if not is_closing:
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag[1])
                parts.append("\n" + "#" * level + " ")
            elif tag == "p":
                parts.append("\n\n")
            elif tag == "br":
                parts.append("\n")
            elif tag in ("strong", "b"):
                parts.append("**")
            elif tag in ("em", "i"):
                parts.append("*")
            elif tag == "a":
                attrs = dict(_ATTR_RE.findall(attrs_str))
                pending_href = attrs.get("href", "")
                parts.append("[")
            elif tag == "li":
                parts.append("\n- ")
            elif tag in ("ul", "ol"):
                parts.append("\n")
            elif tag == "code":
                parts.append("`")
            elif tag == "pre":
                parts.append("\n```\n")
            elif tag == "blockquote":
                parts.append("\n> ")
            elif tag == "hr":
                parts.append("\n---\n")
        else:
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                parts.append("\n")
            elif tag == "p":
                parts.append("\n")
            elif tag in ("strong", "b"):
                parts.append("**")
            elif tag in ("em", "i"):
                parts.append("*")
            elif tag == "a":
                parts.append(f"]({pending_href or ''})")
                pending_href = None
            elif tag == "code":
                parts.append("`")
            elif tag == "pre":
                parts.append("\n```\n")

    if last_end < len(content):
        parts.append(content[last_end:])

    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def html(content: str, operation: str = "to_text") -> str:
    """Process HTML content.

    Operations:

    - ``"to_text"``: strip all HTML tags, return plain text.
    - ``"to_markdown"``: convert basic HTML to Markdown
      (h1→#, h2→##, p→newline, a→[text](href), strong→**, em→*).
    """
    if operation == "to_text":
        text = re.sub(r"<[^>]+>", "", content)
        return _unescape(text).strip()
    elif operation == "to_markdown":
        return _html_to_markdown(content)
    else:
        return content


# Self-register with the global binding registry
bind_function(
    name="html",
    rust_symbol="omg_natives::html::html",
    python_fallback=html,
    type_hints={"content": "str", "operation": "str"},
)
