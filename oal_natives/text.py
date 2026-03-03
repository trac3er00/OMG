"""OMG Natives — text: ANSI-aware text operations.

Pure-Python fallback for text normalization, ANSI stripping, and counting.
Uses ``re`` for ANSI escape code removal.

Feature flag: ``OMG_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import re

from omg_natives._bindings import bind_function

# ANSI escape code pattern (covers CSI sequences, OSC, etc.)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b[^[\]()]")


def text(content: str, operation: str = "normalize") -> str:
    """Perform text operations on *content*.

    Supported operations:

    - ``"normalize"``: strip ANSI codes and normalize whitespace
    - ``"strip_ansi"``: remove ANSI escape codes only
    - ``"word_count"``: return word count as a string
    - ``"line_count"``: return line count as a string
    """
    if operation == "strip_ansi":
        return _ANSI_RE.sub("", content)
    elif operation == "normalize":
        stripped = _ANSI_RE.sub("", content)
        # Normalize whitespace: collapse runs, strip leading/trailing
        return " ".join(stripped.split())
    elif operation == "word_count":
        clean = _ANSI_RE.sub("", content)
        return str(len(clean.split()))
    elif operation == "line_count":
        return str(content.count("\n") + (1 if content and not content.endswith("\n") else 0))
    else:
        return content


# Self-register with the global binding registry
bind_function(
    name="text",
    rust_symbol="omg_natives::text::text",
    python_fallback=text,
    type_hints={"content": "str", "operation": "str"},
)
