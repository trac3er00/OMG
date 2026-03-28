"""OMG Natives — Rust-accelerated hot paths with pure-Python fallbacks.

When the Rust binary is built and installed (via ``maturin develop``),
this package delegates to the compiled ``omg_natives._native`` extension.
Otherwise, every public function falls back to a pure-Python implementation
so that OMG works identically — just slower on CPU-intensive paths.

Feature flag: ``OMG_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import fnmatch as _fnmatch
import logging
import os as _os
import re as _re
import sys as _sys
from pathlib import Path as _Path
from typing import List, Optional


_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flag — follows the hooks/_common.get_feature_flag pattern
# ---------------------------------------------------------------------------

def _get_feature_flag(flag_name: str, default: bool = False) -> bool:
    """Minimal feature-flag check (env var only, no settings.json dependency).

    Mirrors the resolution logic of ``hooks/_common.get_feature_flag`` but
    avoids importing hooks internals so this package stays self-contained.
    """
    env_key = f"OMG_{flag_name.upper()}_ENABLED"
    env_val = _os.environ.get(env_key, "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    # Try full get_feature_flag if available
    try:
        project_root = str(_Path(__file__).resolve().parent.parent)
        if project_root not in _sys.path:
            _sys.path.insert(0, project_root)
        from hooks._common import get_feature_flag  # type: ignore[import-untyped]
        return get_feature_flag(flag_name, default=default)
    except Exception:
        return default


OMG_RUST_ENABLED: bool = _get_feature_flag("RUST_ENGINE", default=False)

# ---------------------------------------------------------------------------
# Try importing compiled Rust extension
# ---------------------------------------------------------------------------

RUST_AVAILABLE: bool = False

if OMG_RUST_ENABLED:
    try:
        from omg_natives._native import *  # noqa: F401, F403
        RUST_AVAILABLE = True
    except ImportError:
        RUST_AVAILABLE = False

# ---------------------------------------------------------------------------
# Pure-Python fallback implementations
# ---------------------------------------------------------------------------

if not RUST_AVAILABLE:

    def grep(pattern: str, path: str) -> List[str]:
        """Search for *pattern* (regex) in the file at *path*.

        Returns a list of matching lines (without trailing newline).
        """
        matches: List[str] = []
        try:
            compiled = _re.compile(pattern)
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if compiled.search(line):
                        matches.append(line.rstrip("\n"))
        except (OSError, _re.error) as exc:
            _logger.debug("Native grep fallback failed for %s: %s", path, exc, exc_info=True)
        return matches

    def glob_match(pattern: str, base: str = ".") -> List[str]:
        """Return file paths under *base* that match the glob *pattern*.

        Pure-Python implementation using ``os.walk`` + ``fnmatch``.
        """
        results: List[str] = []
        base_path = _Path(base).resolve()
        try:
            for root, _dirs, files in _os.walk(base_path):
                for name in files:
                    full = _os.path.join(root, name)
                    rel = _os.path.relpath(full, base_path)
                    if _fnmatch.fnmatch(rel, pattern):
                        results.append(rel)
        except OSError as exc:
            _logger.debug("Native glob fallback walk failed for %s: %s", base_path, exc, exc_info=True)
        return results

    def normalize(text: str) -> str:
        """Normalize whitespace and line endings in *text*."""
        return text.replace("\r\n", "\n").strip()

    def highlight_syntax(code: str, language: str = "") -> str:
        """Return *code* unchanged (no highlighting without Rust)."""
        _ = language
        return code

    def strip_tags(html: str) -> str:
        """Strip HTML tags from *html*, returning plain text."""
        return _re.sub(r"<[^>]+>", "", html)

# ---------------------------------------------------------------------------
# N-API Binding Registry (Task 5.2)
# ---------------------------------------------------------------------------

from omg_natives._bindings import (  # noqa: E402
    REGISTRY,
    BindingRegistry,
    BindingSpec,
    bind_function,
    call_binding,
    get_binding,
    marshal_from_rust,
    marshal_to_rust,
)

# ---------------------------------------------------------------------------
# Task 5.3: Import 12 module fallbacks (self-register via bind_function)
# Each module self-registers with REGISTRY at import time.
# Note: grep module imported without shadowing legacy grep(pattern, path)->List[str]
# ---------------------------------------------------------------------------

# Save legacy functions that module imports would shadow
_legacy_grep = grep  # type: ignore[possibly-undefined]  # noqa: E402

import omg_natives.grep as _grep_mod  # noqa: E402, F401
from omg_natives.glob import glob as glob  # noqa: E402
from omg_natives.shell import shell  # noqa: E402
from omg_natives.text import text as text  # noqa: E402
from omg_natives.keys import keys  # noqa: E402
from omg_natives.highlight import highlight  # noqa: E402
from omg_natives.task import task_run  # noqa: E402
from omg_natives.ps import ps  # noqa: E402
from omg_natives.prof import prof  # noqa: E402
from omg_natives.image import image  # noqa: E402
from omg_natives.clipboard import clipboard  # noqa: E402
from omg_natives.html import html  # noqa: E402

# Restore legacy grep (returns List[str] for backward compat)
grep = _legacy_grep  # type: ignore[assignment]  # noqa: E402

# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

__all__ = [
    "OMG_RUST_ENABLED",
    "RUST_AVAILABLE",
    "grep",
    "glob_match",
    "normalize",
    "highlight_syntax",
    "strip_tags",
    # N-API Binding Registry
    "REGISTRY",
    "BindingRegistry",
    "BindingSpec",
    "bind_function",
    "call_binding",
    "get_binding",
    "marshal_from_rust",
    "marshal_to_rust",
    # Task 5.3: 12 Core Module Functions
    "glob",
    "shell",
    "text",
    "keys",
    "highlight",
    "task_run",
    "ps",
    "prof",
    "image",
    "clipboard",
    "html",
]
