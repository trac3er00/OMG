"""OAL Natives — glob: file path matching.

Pure-Python fallback for the Rust ``oal_natives::glob::glob_match`` function.
Uses ``pathlib.Path.glob`` for pattern matching.

Feature flag: ``OAL_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from oal_natives._bindings import bind_function


def glob(pattern: str, base: str = ".") -> list[str]:
    """Return file paths under *base* that match the glob *pattern*.

    Uses ``pathlib.Path.glob`` for matching.
    Returns relative paths as strings.
    """
    results: List[str] = []
    base_path = Path(base).resolve()
    try:
        for match in base_path.glob(pattern):
            try:
                results.append(str(match.relative_to(base_path)))
            except ValueError:
                results.append(str(match))
    except OSError:
        pass
    return results


# Self-register with the global binding registry
bind_function(
    name="glob",
    rust_symbol="oal_natives::glob::glob_match",
    python_fallback=glob,
    type_hints={"pattern": "str", "base": "str"},
)
