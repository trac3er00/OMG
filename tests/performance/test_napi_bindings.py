"""Tests for oal_natives N-API binding registry and marshalling utilities.

Verifies:
- BindingRegistry register / get / call / list_names / is_rust_available
- marshal_to_rust and marshal_from_rust type conversion
- Module-level convenience wrappers (bind_function, get_binding, call_binding)
"""

from __future__ import annotations

import pytest

from oal_natives._bindings import (
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
# Helpers
# ---------------------------------------------------------------------------

def _py_add(a: int, b: int) -> int:
    """Trivial fallback for testing."""
    return a + b


def _py_upper(text: str) -> str:
    """Trivial fallback for testing."""
    return text.upper()


def _py_identity(x):
    """Return input unchanged."""
    return x


# ---------------------------------------------------------------------------
# Registry: register / get / call / list / is_rust_available
# ---------------------------------------------------------------------------

class TestRegistryRegisterAndGet:
    """Register a binding and retrieve it."""

    def test_registry_register_and_get(self):
        reg = BindingRegistry()
        reg.register("add", "oal_natives::math::add", _py_add, {"a": "int", "b": "int"})

        spec = reg.get("add")
        assert spec is not None
        assert isinstance(spec, BindingSpec)
        assert spec.name == "add"
        assert spec.rust_symbol == "oal_natives::math::add"
        assert spec.python_fallback is _py_add
        assert spec.type_hints == {"a": "int", "b": "int"}

    def test_registry_get_missing_returns_none(self):
        reg = BindingRegistry()
        assert reg.get("nonexistent") is None


class TestRegistryListNames:
    """List registered binding names."""

    def test_registry_list_names(self):
        reg = BindingRegistry()
        reg.register("beta", "rs::beta", _py_identity)
        reg.register("alpha", "rs::alpha", _py_identity)
        reg.register("gamma", "rs::gamma", _py_identity)

        names = reg.list_names()
        assert names == ["alpha", "beta", "gamma"]  # sorted

    def test_registry_list_names_empty(self):
        reg = BindingRegistry()
        assert reg.list_names() == []


class TestRegistryCallPythonFallback:
    """Call a binding and verify python_fallback is invoked."""

    def test_registry_call_python_fallback(self):
        reg = BindingRegistry()
        reg.register("add", "rs::add", _py_add)

        result = reg.call("add", 3, 7)
        assert result == 10

    def test_registry_call_with_kwargs(self):
        def _kw_fn(*, name: str) -> str:
            return f"hello {name}"

        reg = BindingRegistry()
        reg.register("greet", "rs::greet", _kw_fn)

        assert reg.call("greet", name="world") == "hello world"

    def test_registry_call_missing_raises(self):
        reg = BindingRegistry()
        with pytest.raises(KeyError, match="No binding registered"):
            reg.call("missing")


# ---------------------------------------------------------------------------
# Marshalling
# ---------------------------------------------------------------------------

class TestMarshalToRust:
    """marshal_to_rust type conversion."""

    def test_marshal_to_rust_str(self):
        assert marshal_to_rust("hello") == "hello"

    def test_marshal_to_rust_list(self):
        data = [1, 2, 3]
        assert marshal_to_rust(data) == [1, 2, 3]
        assert marshal_to_rust(data) is data  # identity in fallback mode

    def test_marshal_to_rust_dict(self):
        data = {"key": "value"}
        assert marshal_to_rust(data) == {"key": "value"}
        assert marshal_to_rust(data) is data

    def test_marshal_to_rust_int(self):
        assert marshal_to_rust(42) == 42

    def test_marshal_to_rust_float(self):
        assert marshal_to_rust(3.14) == 3.14

    def test_marshal_to_rust_bool(self):
        assert marshal_to_rust(True) is True
        assert marshal_to_rust(False) is False

    def test_marshal_to_rust_bytes(self):
        data = b"\x00\x01\x02"
        assert marshal_to_rust(data) == b"\x00\x01\x02"

    def test_marshal_to_rust_none(self):
        assert marshal_to_rust(None) is None

    def test_marshal_to_rust_unsupported_raises(self):
        with pytest.raises(TypeError, match="Unsupported type"):
            marshal_to_rust(object())


class TestMarshalFromRust:
    """marshal_from_rust is identity in Python fallback mode."""

    def test_marshal_from_rust_identity(self):
        for value in ("hello", [1, 2], {"k": "v"}, 42, 3.14, True, b"\x00", None):
            assert marshal_from_rust(value) is value

    def test_marshal_from_rust_arbitrary_object(self):
        """from_rust accepts anything (no type restriction on Rust side)."""
        obj = object()
        assert marshal_from_rust(obj) is obj


# ---------------------------------------------------------------------------
# is_rust_available
# ---------------------------------------------------------------------------

class TestIsRustAvailable:
    """is_rust_available always returns False in Python fallback mode."""

    def test_is_rust_available_false(self):
        reg = BindingRegistry()
        reg.register("fn", "rs::fn", _py_identity)
        assert reg.is_rust_available("fn") is False

    def test_is_rust_available_unregistered(self):
        reg = BindingRegistry()
        assert reg.is_rust_available("nonexistent") is False


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------

class TestConvenienceWrappers:
    """Test bind_function, get_binding, call_binding using global REGISTRY."""

    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        """Ensure tests don't leak bindings into the global registry."""
        original = dict(REGISTRY._bindings)
        yield
        REGISTRY._bindings.clear()
        REGISTRY._bindings.update(original)

    def test_bind_function_convenience(self):
        bind_function("upper", "rs::upper", _py_upper, {"text": "str"})

        spec = REGISTRY.get("upper")
        assert spec is not None
        assert spec.name == "upper"
        assert spec.python_fallback is _py_upper

    def test_get_binding_convenience(self):
        bind_function("add2", "rs::add2", _py_add)

        spec = get_binding("add2")
        assert spec is not None
        assert spec.rust_symbol == "rs::add2"

    def test_get_binding_missing(self):
        assert get_binding("does_not_exist") is None

    def test_call_binding_convenience(self):
        bind_function("add3", "rs::add3", _py_add)

        result = call_binding("add3", 10, 20)
        assert result == 30


# ---------------------------------------------------------------------------
# BindingSpec dataclass
# ---------------------------------------------------------------------------

class TestBindingSpec:
    """BindingSpec dataclass field defaults and construction."""

    def test_default_type_hints(self):
        spec = BindingSpec(name="f", rust_symbol="rs::f", python_fallback=_py_identity)
        assert spec.type_hints == {}

    def test_explicit_type_hints(self):
        hints = {"x": "int", "y": "float"}
        spec = BindingSpec(
            name="f", rust_symbol="rs::f", python_fallback=_py_identity, type_hints=hints
        )
        assert spec.type_hints == hints

    def test_register_overwrites(self):
        """Registering the same name twice overwrites the previous spec."""
        reg = BindingRegistry()
        reg.register("fn", "rs::fn_v1", _py_add)
        reg.register("fn", "rs::fn_v2", _py_upper)

        spec = reg.get("fn")
        assert spec is not None
        assert spec.rust_symbol == "rs::fn_v2"
        assert spec.python_fallback is _py_upper


# ---------------------------------------------------------------------------
# Integration: oal_natives re-exports
# ---------------------------------------------------------------------------

class TestOalNativesReExports:
    """Verify oal_natives.__init__ re-exports the binding API."""

    def test_import_from_oal_natives(self):
        import oal_natives

        assert hasattr(oal_natives, "REGISTRY")
        assert hasattr(oal_natives, "bind_function")
        assert hasattr(oal_natives, "get_binding")
        assert hasattr(oal_natives, "call_binding")
        assert hasattr(oal_natives, "marshal_to_rust")
        assert hasattr(oal_natives, "marshal_from_rust")
        assert hasattr(oal_natives, "BindingSpec")
        assert hasattr(oal_natives, "BindingRegistry")

    def test_all_includes_bindings(self):
        import oal_natives

        for name in ("REGISTRY", "bind_function", "get_binding", "call_binding",
                      "marshal_to_rust", "marshal_from_rust", "BindingSpec", "BindingRegistry"):
            assert name in oal_natives.__all__, f"{name} missing from __all__"
