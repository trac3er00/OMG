from __future__ import annotations

from collections.abc import Callable
import importlib.util
from pathlib import Path
from typing import cast

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "memory_schema.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "runtime.memory_schema", MODULE_PATH
)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
MEMORY_SCHEMA = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MEMORY_SCHEMA)

ValidateFn = Callable[[str, dict[str, object]], None]
DescribeFn = Callable[[str], str]

CATEGORIES = (
    "decisions",
    "preferences",
    "failures",
    "open_loops",
    "team_context",
)
SchemaValidationError = cast(type[Exception], MEMORY_SCHEMA.SchemaValidationError)
get_schema_description = cast(DescribeFn, MEMORY_SCHEMA.get_schema_description)
validate = cast(ValidateFn, MEMORY_SCHEMA.validate)


def test_valid_decisions_entry() -> None:
    validate("decisions", {"decision": "Use PostgreSQL", "rationale": "Team expertise"})


def test_valid_preferences_entry() -> None:
    validate("preferences", {"preference": "naming_style", "value": "camelCase"})


def test_valid_failures_entry() -> None:
    validate("failures", {"what": "auth failed", "why": "wrong key"})


def test_valid_open_loops_entry() -> None:
    validate("open_loops", {"task": "Add pagination", "status": "pending"})


def test_valid_team_context_entry() -> None:
    validate("team_context", {"member": "alice", "role": "developer"})


def test_missing_required_field_raises() -> None:
    with pytest.raises(SchemaValidationError) as exc_info:
        validate("decisions", {"decision": "Use JWT"})
    assert "rationale" in str(exc_info.value)


def test_wrong_type_raises() -> None:
    with pytest.raises(SchemaValidationError) as exc_info:
        validate("decisions", {"decision": 123, "rationale": "test"})
    assert "str" in str(exc_info.value)


def test_unknown_category_raises() -> None:
    with pytest.raises(SchemaValidationError) as exc_info:
        validate("invalid_category", {"x": "y"})
    assert "Unknown category" in str(exc_info.value)


def test_unknown_field_raises() -> None:
    with pytest.raises(SchemaValidationError) as exc_info:
        validate("decisions", {"decision": "x", "rationale": "y", "alien_field": "z"})
    assert "Unknown fields" in str(exc_info.value)


def test_optional_fields_accepted() -> None:
    validate(
        "decisions",
        {"decision": "x", "rationale": "y", "tags": ["tag1"], "confidence": 0.9},
    )


def test_get_schema_description() -> None:
    desc = get_schema_description("decisions")
    assert "decisions" in desc
    assert "decision" in desc
    assert "rationale" in desc


def test_all_categories_valid() -> None:
    for category in CATEGORIES:
        desc = get_schema_description(category)
        assert category in desc
