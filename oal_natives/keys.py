"""OAL Natives — keys: keyboard protocol stubs.

Pure-Python stub for keyboard key listing and encoding.
No actual keyboard interaction — returns static data.

Feature flag: ``OAL_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

from typing import List

from oal_natives._bindings import bind_function

# Common key names for the stub
_COMMON_KEYS: List[str] = [
    "Enter", "Escape", "Tab", "Backspace", "Delete",
    "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    "Home", "End", "PageUp", "PageDown",
    "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "F9", "F10", "F11", "F12",
    "Space", "Insert", "PrintScreen", "ScrollLock", "Pause",
]


def keys(operation: str = "list") -> list[str]:
    """Keyboard protocol stubs.

    - ``"list"``: returns a list of common key names.
    - ``"encode"``: returns an empty list (stub).
    """
    if operation == "list":
        return list(_COMMON_KEYS)
    elif operation == "encode":
        return []
    else:
        return []


# Self-register with the global binding registry
bind_function(
    name="keys",
    rust_symbol="oal_natives::keys::keys",
    python_fallback=keys,
    type_hints={"operation": "str"},
)
