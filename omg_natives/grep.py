"""OMG Natives — grep: regex search in files.

Pure-Python fallback for the Rust ``omg_natives::grep::grep`` function.
Uses ``re`` and ``os.walk`` for recursive file searching.

Feature flag: ``OMG_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import logging
import os
import re
from typing import List

from omg_natives._bindings import bind_function


_logger = logging.getLogger(__name__)


def grep(pattern: str, path: str, recursive: bool = False) -> list[dict]:
    """Search for *pattern* (regex) in files.

    If *recursive* is False, searches only the single file at *path*.
    If *recursive* is True and *path* is a directory, walks the directory tree.

    Returns a list of ``{"file": path, "line": lineno, "text": line_content}``.
    """
    results: List[dict] = []
    try:
        compiled = re.compile(pattern)
    except re.error:
        return results

    def _search_file(filepath: str) -> None:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if compiled.search(line):
                        results.append({
                            "file": filepath,
                            "line": lineno,
                            "text": line.rstrip("\n"),
                        })
        except OSError as exc:
            _logger.debug("Failed to read file during grep fallback %s: %s", filepath, exc, exc_info=True)

    if recursive and os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for name in files:
                _search_file(os.path.join(root, name))
    else:
        _search_file(path)

    return results


# Self-register with the global binding registry
bind_function(
    name="grep",
    rust_symbol="omg_natives::grep::grep",
    python_fallback=grep,
    type_hints={"pattern": "str", "path": "str", "recursive": "bool"},
)
