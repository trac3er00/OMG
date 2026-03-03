"""N-API Binding Registry — maps function names to (rust_fn_spec, python_fallback) pairs.

Provides a registry for Rust↔Python bindings with marshalling utilities.
When Rust is not available, all calls transparently use the Python fallback.

This module is pure stdlib — no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# BindingSpec — describes a single Rust↔Python binding
# ---------------------------------------------------------------------------

@dataclass
class BindingSpec:
    """Specification for a single Rust↔Python binding.

    Attributes:
        name: Logical name of the binding (e.g. ``"grep"``).
        rust_symbol: Rust symbol path (e.g. ``"oal_natives::grep::grep"``).
        python_fallback: Callable Python implementation used when Rust is unavailable.
        type_hints: Optional mapping of parameter names to type strings for
            documentation and marshalling guidance.
    """

    name: str
    rust_symbol: str
    python_fallback: Callable[..., Any]
    type_hints: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Marshalling utilities — Rust↔Python data type conversion
# ---------------------------------------------------------------------------

# Supported types for Rust↔Python marshalling.
_SUPPORTED_TYPES = (str, list, dict, int, float, bool, bytes, type(None))


def marshal_to_rust(value: Any) -> Any:
    """Convert a Python value to a Rust-compatible representation.

    In the current pure-Python fallback mode this is an identity operation
    for all supported types (str, list, dict, int, float, bool, bytes, None).

    Raises:
        TypeError: If *value* is not a supported type.
    """
    if not isinstance(value, _SUPPORTED_TYPES):
        raise TypeError(
            f"Unsupported type for Rust marshalling: {type(value).__name__}. "
            f"Supported: str, list, dict, int, float, bool, bytes, None"
        )
    return value


def marshal_from_rust(value: Any) -> Any:
    """Convert a Rust-returned value back to a Python representation.

    In pure-Python fallback mode this is always the identity function
    because no actual FFI boundary is crossed.
    """
    return value


# ---------------------------------------------------------------------------
# BindingRegistry — central store for all registered bindings
# ---------------------------------------------------------------------------

class BindingRegistry:
    """Thread-safe registry mapping binding names to :class:`BindingSpec` instances.

    Usage::

        registry = BindingRegistry()
        registry.register("grep", "oal_natives::grep::grep", _py_grep)
        result = registry.call("grep", pattern, path)
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, BindingSpec] = {}

    # -- mutators -----------------------------------------------------------

    def register(
        self,
        name: str,
        rust_symbol: str,
        python_fallback: Callable[..., Any],
        type_hints: Optional[Dict[str, str]] = None,
    ) -> None:
        """Register a new binding (or overwrite an existing one)."""
        self._bindings[name] = BindingSpec(
            name=name,
            rust_symbol=rust_symbol,
            python_fallback=python_fallback,
            type_hints=type_hints or {},
        )

    # -- accessors ----------------------------------------------------------

    def get(self, name: str) -> Optional[BindingSpec]:
        """Return the :class:`BindingSpec` for *name*, or ``None``."""
        return self._bindings.get(name)

    def list_names(self) -> List[str]:
        """Return a sorted list of all registered binding names."""
        return sorted(self._bindings.keys())

    def is_rust_available(self, name: str) -> bool:
        """Check whether the Rust implementation is available for *name*.

        Always returns ``False`` in pure-Python fallback mode.
        """
        # In a real Rust-enabled build this would probe the native extension.
        return False

    # -- invocation ---------------------------------------------------------

    def call(self, __name: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke the binding identified by *__name*.

        In pure-Python fallback mode this delegates directly to the
        registered ``python_fallback`` callable.

        Raises:
            KeyError: If no binding with *__name* is registered.
        """
        spec = self._bindings.get(__name)
        if spec is None:
            raise KeyError(f"No binding registered with name: {__name!r}")
        return spec.python_fallback(*args, **kwargs)


# ---------------------------------------------------------------------------
# Module-level singleton and convenience wrappers
# ---------------------------------------------------------------------------

REGISTRY = BindingRegistry()
"""Module-level singleton :class:`BindingRegistry` instance."""


def bind_function(
    name: str,
    rust_symbol: str,
    python_fallback: Callable[..., Any],
    type_hints: Optional[Dict[str, str]] = None,
) -> None:
    """Convenience wrapper — register a binding in the global :data:`REGISTRY`."""
    REGISTRY.register(name, rust_symbol, python_fallback, type_hints=type_hints)


def get_binding(name: str) -> Optional[BindingSpec]:
    """Convenience wrapper — look up a binding in the global :data:`REGISTRY`."""
    return REGISTRY.get(name)


def call_binding(__name: str, *args: Any, **kwargs: Any) -> Any:
    """Convenience wrapper — invoke a binding via the global :data:`REGISTRY`."""
    return REGISTRY.call(__name, *args, **kwargs)
