"""OAL Natives — clipboard: clipboard operation stubs.

Pure-Python stubs for clipboard operations.
No actual clipboard interaction — returns placeholder values.

Feature flag: ``OAL_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

from typing import Optional

from oal_natives._bindings import bind_function


def clipboard(operation: str = "get", text: Optional[str] = None) -> str:
    """Clipboard operation stubs.

    - ``"get"``: returns ``""`` (stub — no actual clipboard access).
    - ``"set"``: returns ``"ok"`` (stub — no actual clipboard access).
    """
    if operation == "get":
        return ""
    elif operation == "set":
        return "ok"
    else:
        return ""


# Self-register with the global binding registry
bind_function(
    name="clipboard",
    rust_symbol="oal_natives::clipboard::clipboard",
    python_fallback=clipboard,
    type_hints={"operation": "str", "text": "str"},
)
