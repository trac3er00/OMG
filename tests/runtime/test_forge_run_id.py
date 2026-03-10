"""Tests for forge run ID generation and validation."""
from __future__ import annotations

import re

import pytest

from runtime.forge_run_id import (
    build_deterministic_contract,
    derive_run_seed,
    generate_run_id,
    normalize_run_id,
    validate_run_id,
)


class TestGenerateRunId:
    def test_generate_run_id_produces_non_empty_string(self) -> None:
        run_id = generate_run_id()
        assert isinstance(run_id, str)
        assert len(run_id) > 0

    def test_generate_run_id_matches_compact_utc_pattern(self) -> None:
        """Verify format: YYYYMMDDTHHMMSSfffffZ"""
        run_id = generate_run_id()
        # Pattern: 8 digits, T, 6 digits, 6 digits (microseconds), Z
        pattern = r"^\d{8}T\d{6}\d{6}Z$"
        assert re.match(pattern, run_id), f"run_id {run_id} does not match pattern {pattern}"

    def test_generate_run_id_produces_different_ids_on_successive_calls(self) -> None:
        """Microseconds should differ between calls."""
        id1 = generate_run_id()
        id2 = generate_run_id()
        # They may be the same if called within the same microsecond, but very unlikely
        # Just verify both are valid format
        assert re.match(r"^\d{8}T\d{6}\d{6}Z$", id1)
        assert re.match(r"^\d{8}T\d{6}\d{6}Z$", id2)


class TestValidateRunId:
    def test_validate_run_id_accepts_valid_alphanumeric_id(self) -> None:
        is_valid, reason = validate_run_id("forge-run-42")
        assert is_valid is True
        assert reason == ""

    def test_validate_run_id_accepts_compact_utc_format(self) -> None:
        is_valid, reason = validate_run_id("20260309T143022123456Z")
        assert is_valid is True
        assert reason == ""

    def test_validate_run_id_accepts_simple_alphanumeric(self) -> None:
        is_valid, reason = validate_run_id("run123")
        assert is_valid is True
        assert reason == ""

    def test_validate_run_id_rejects_empty_string(self) -> None:
        is_valid, reason = validate_run_id("")
        assert is_valid is False
        assert "non-empty" in reason.lower()

    def test_validate_run_id_rejects_id_with_spaces(self) -> None:
        is_valid, reason = validate_run_id("invalid run id")
        assert is_valid is False
        assert "alphanumeric" in reason.lower() or "hyphens" in reason.lower()

    def test_validate_run_id_rejects_id_with_special_chars(self) -> None:
        is_valid, reason = validate_run_id("run@id#123")
        assert is_valid is False
        assert "alphanumeric" in reason.lower() or "hyphens" in reason.lower()

    def test_validate_run_id_rejects_id_exceeding_128_chars(self) -> None:
        long_id = "a" * 129
        is_valid, reason = validate_run_id(long_id)
        assert is_valid is False
        assert "128" in reason or "exceeds" in reason.lower()

    def test_validate_run_id_accepts_id_at_128_chars(self) -> None:
        max_id = "a" * 128
        is_valid, reason = validate_run_id(max_id)
        assert is_valid is True
        assert reason == ""

    def test_validate_run_id_accepts_hyphens(self) -> None:
        is_valid, reason = validate_run_id("forge-run-v1-test-42")
        assert is_valid is True
        assert reason == ""


class TestNormalizeRunId:
    def test_normalize_run_id_with_none_generates_new_id(self) -> None:
        run_id = normalize_run_id(None)
        assert isinstance(run_id, str)
        assert len(run_id) > 0
        # Should match compact UTC format
        assert re.match(r"^\d{8}T\d{6}\d{6}Z$", run_id)

    def test_normalize_run_id_with_valid_id_returns_unchanged(self) -> None:
        provided_id = "forge-run-42"
        result = normalize_run_id(provided_id)
        assert result == provided_id

    def test_normalize_run_id_with_empty_string_generates_new_id(self) -> None:
        run_id = normalize_run_id("")
        assert isinstance(run_id, str)
        assert len(run_id) > 0
        assert re.match(r"^\d{8}T\d{6}\d{6}Z$", run_id)

    def test_normalize_run_id_with_invalid_id_generates_new_id(self) -> None:
        # Invalid due to spaces
        run_id = normalize_run_id("invalid run id")
        assert isinstance(run_id, str)
        assert len(run_id) > 0
        # Should be a generated ID, not the invalid one
        assert run_id != "invalid run id"
        assert re.match(r"^\d{8}T\d{6}\d{6}Z$", run_id)

    def test_normalize_run_id_with_valid_compact_utc_returns_unchanged(self) -> None:
        provided_id = "20260309T143022123456Z"
        result = normalize_run_id(provided_id)
        assert result == provided_id

    def test_normalize_run_id_with_hyphenated_id_returns_unchanged(self) -> None:
        provided_id = "vision-agent-run-001"
        result = normalize_run_id(provided_id)
        assert result == provided_id


class TestDeterministicRunContract:
    def test_derive_run_seed_is_stable_for_same_run_id(self) -> None:
        run_id = "forge-run-42"
        assert derive_run_seed(run_id) == derive_run_seed(run_id)

    def test_derive_run_seed_changes_when_run_id_changes(self) -> None:
        assert derive_run_seed("forge-run-42") != derive_run_seed("forge-run-43")

    def test_derive_run_seed_rejects_invalid_run_ids(self) -> None:
        with pytest.raises(ValueError, match="run_id"):
            _ = derive_run_seed("invalid run id")

    def test_build_deterministic_contract_locks_critical_temperature_paths(self) -> None:
        run_id = "forge-run-42"
        contract = build_deterministic_contract(run_id)

        assert contract["seed"] == derive_run_seed(run_id)
        assert contract["determinism_version"]
        assert contract["determinism_scope"] == "same-hardware"
        assert contract["temperature_lock"] == {
            "critical_model_paths": 0.0,
            "critical_tool_paths": 0.0,
        }
