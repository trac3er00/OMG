"""OAL Natives — prof: profiling wrapper.

Pure-Python fallback for simple function profiling.
Uses ``time.perf_counter`` for high-resolution timing.

Feature flag: ``OAL_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import time
from typing import Any, Callable

from oal_natives._bindings import bind_function


def prof(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> dict:
    """Profile the execution of *fn(*args, **kwargs)*.

    Returns ``{"result": value, "elapsed_ms": float, "error": None}`` on success,
    or ``{"result": None, "elapsed_ms": float, "error": str}`` on failure.
    """
    start = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000.0
        return {"result": result, "elapsed_ms": elapsed, "error": None}
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return {"result": None, "elapsed_ms": elapsed, "error": str(exc)}


# Self-register with the global binding registry
bind_function(
    name="prof",
    rust_symbol="oal_natives::prof::prof",
    python_fallback=prof,
    type_hints={"fn": "callable"},
)
