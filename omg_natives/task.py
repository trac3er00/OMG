"""OMG Natives — task: concurrent.futures thread pool execution.

Pure-Python fallback using ``concurrent.futures.ThreadPoolExecutor``
for running callables in a background thread with timeout support.

Feature flag: ``OMG_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from omg_natives._bindings import bind_function


def task_run(fn: Callable[..., Any], *args: Any, timeout: float = 30.0) -> dict:
    """Run *fn(*args)* in a ``ThreadPoolExecutor``.

    Returns ``{"result": value, "error": None}`` on success,
    or ``{"result": None, "error": str}`` on failure.
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args)
            result = future.result(timeout=timeout)
            return {"result": result, "error": None}
    except FuturesTimeoutError:
        return {"result": None, "error": f"Task timed out after {timeout}s"}
    except Exception as exc:
        return {"result": None, "error": str(exc)}


# Self-register with the global binding registry
# Note: function is 'task_run' to avoid shadowing Python's 'task' concept
bind_function(
    name="task_run",
    rust_symbol="omg_natives::task::task_run",
    python_fallback=task_run,
    type_hints={"fn": "callable", "timeout": "float"},
)
