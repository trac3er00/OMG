"""Tests for edge case synthesizer plugin."""

from __future__ import annotations

import ast
import sys

from plugins.testgen.edge_case_synthesizer import synthesize_edge_cases


def _joined_cases(signature: str, framework: str) -> str:
    return "\n".join(synthesize_edge_cases(signature, framework))


def test_null_input_cases_generated() -> None:
    cases = _joined_cases("def process(items: list, limit: int = 100) -> dict", "pytest")
    assert "None" in cases
    assert "items=None" in cases
    assert "limit=None" in cases


def test_empty_collection_cases_generated() -> None:
    cases = _joined_cases("def process(items: list, cfg: dict, name: str) -> dict", "pytest")
    assert "items=[]" in cases
    assert "cfg={}" in cases
    assert "name=''" in cases


def test_boundary_value_cases_generated() -> None:
    cases = _joined_cases("def process(limit: int, retries: int = 3) -> dict", "pytest")
    assert "limit=0" in cases or "retries=0" in cases
    assert "limit=-1" in cases or "retries=-1" in cases
    assert str(sys.maxsize) in cases


def test_type_mismatch_cases_generated() -> None:
    cases = _joined_cases("def process(items: list, limit: int, enabled: bool) -> dict", "pytest")
    assert "items='wrong_type'" in cases
    assert "limit='wrong_type'" in cases
    assert "enabled='wrong_type'" in cases


def test_pytest_syntax_valid() -> None:
    tests = synthesize_edge_cases("def process(items: list, limit: int = 100) -> dict", "pytest")
    assert tests
    for code in tests:
        _ = ast.parse(code)
        assert code.startswith("def test_process_")


def test_jest_syntax_generated() -> None:
    tests = synthesize_edge_cases("def process(items: list, limit: int = 100) -> dict", "jest")
    assert tests
    joined = "\n".join(tests)
    assert "it('should handle" in joined
    assert "expect(() => process(" in joined
    assert "toThrow" in joined


def test_large_input_cases_generated() -> None:
    cases = _joined_cases("def process(items: list, payload: str) -> dict", "pytest")
    assert "items=[0] * 10000" in cases
    assert "payload='x' * 10000" in cases
