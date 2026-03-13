"""Tests for tiered token estimation module."""
from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

import pytest

# Add hooks to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hooks"))

HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"
MODULE_PATH = HOOKS_DIR / "_token_counter.py"
spec = importlib.util.spec_from_file_location("_token_counter", MODULE_PATH)
assert spec is not None and spec.loader is not None
_token_counter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_token_counter)


def test_estimate_tokens_tier1_uses_expected_heuristic_formula():
    text = "Hello world, this is a test."
    expected = max(1, int(len(text) / 3.5))
    assert _token_counter.estimate_tokens(text, tier=1) == expected


def test_estimate_tokens_tier1_handles_empty_string_without_crashing():
    result = _token_counter.estimate_tokens("", tier=1)
    assert result in (0, 1)


def test_estimate_tokens_tier2_returns_integer_for_code_text():
    result = _token_counter.estimate_tokens("def hello():\n    return 1\n", tier=2)
    assert isinstance(result, int)
    assert result >= 1


def test_estimate_tokens_tier2_handles_empty_string_without_crashing():
    result = _token_counter.estimate_tokens("", tier=2)
    assert result in (0, 1)


def test_estimate_tokens_invalid_tier_does_not_raise_and_returns_int():
    result = _token_counter.estimate_tokens("abc", tier=999)
    assert isinstance(result, int)
    assert result >= 0


def test_estimate_tokens_tier3_falls_back_to_tier2_when_api_key_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text = "fallback required when no key"
    assert _token_counter.estimate_tokens(text, tier=3) == _token_counter.estimate_tokens(text, tier=2)


def test_estimate_tokens_tier3_falls_back_to_tier2_on_network_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _raise_error(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr(_token_counter.urllib.request, "urlopen", _raise_error)
    text = "network error fallback"
    assert _token_counter.estimate_tokens(text, tier=3) == _token_counter.estimate_tokens(text, tier=2)


def test_estimate_tokens_tier3_uses_count_tokens_api_result(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"input_tokens": 123}).encode("utf-8")

    monkeypatch.setattr(_token_counter.urllib.request, "urlopen", lambda *_args, **_kwargs: _Resp())
    assert _token_counter.estimate_tokens("api-count", tier=3) == 123


def test_auto_select_tier_ui_display_is_tier1():
    assert _token_counter.auto_select_tier("ui_display", "short") == 1


def test_auto_select_tier_budget_enforcement_is_tier2():
    assert _token_counter.auto_select_tier("budget_enforcement", "short") == 2


def test_auto_select_tier_preflight_large_operation_is_tier3():
    large_text = "x" * 12000
    assert _token_counter.auto_select_tier("preflight", large_text) == 3


def test_auto_select_tier_preflight_small_operation_degrades_to_tier2():
    assert _token_counter.auto_select_tier("preflight", "small") == 2


def test_get_anthropic_api_key_runtime_error_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    """RuntimeError from credential store falls back to ANTHROPIC_API_KEY env var."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-fallback-key")

    def _raise_runtime(*_args, **_kwargs):
        raise RuntimeError("Secure credential backend unavailable: cryptography is required")

    import types
    fake_mod = types.ModuleType("credential_store")
    fake_mod.get_active_key = _raise_runtime  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "credential_store", fake_mod)

    result = _token_counter._get_anthropic_api_key()
    assert result == "env-fallback-key"


def test_get_anthropic_api_key_import_error_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    """ImportError from credential store falls back to ANTHROPIC_API_KEY env var."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-import-key")
    monkeypatch.delitem(sys.modules, "credential_store", raising=False)

    import importlib as _il
    orig_import = _il.import_module

    def _fail_import(name, *args, **kwargs):
        if name == "credential_store":
            raise ImportError("No module named 'credential_store'")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(_il, "import_module", _fail_import)

    result = _token_counter._get_anthropic_api_key()
    assert result == "env-import-key"
