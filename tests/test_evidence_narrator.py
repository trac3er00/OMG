"""Tests for runtime/evidence_narrator.py completion claim validation (NF1b)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from runtime.evidence_narrator import (
    COMPLETION_CLAIM_PATTERNS,
    check_completion_claim_validity,
    matches_completion_claim,
    narrate_missing_evidence,
)


class TestCheckCompletionClaimValidityNoSession:
    """Test check_completion_claim_validity with no active session."""

    def test_no_session_file_allows_completion(self, tmp_path: Path) -> None:
        """No session.json means no active work - completion allowed."""
        result = check_completion_claim_validity(str(tmp_path))

        assert result["allowed"] is True
        assert result["missing"] == []
        assert result["conclusion"] == "verified"
        assert "no active session" in result["reason"].lower()

    def test_empty_session_file_allows_completion(self, tmp_path: Path) -> None:
        """Empty session.json (no run_id) means no active work."""
        session_dir = tmp_path / ".omg" / "state"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text("{}", encoding="utf-8")

        result = check_completion_claim_validity(str(tmp_path))

        assert result["allowed"] is True
        assert result["conclusion"] == "verified"

    def test_malformed_session_json_allows_completion(self, tmp_path: Path) -> None:
        """Malformed session.json is treated as no active session."""
        session_dir = tmp_path / ".omg" / "state"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text("not valid json", encoding="utf-8")

        result = check_completion_claim_validity(str(tmp_path))

        assert result["allowed"] is True


class TestCheckCompletionClaimValidityActiveSessionNoProof:
    """Test check_completion_claim_validity with active session but no proof."""

    def test_active_session_no_proof_blocks_completion(self, tmp_path: Path) -> None:
        """Active session without proof gate verdict blocks completion."""
        session_dir = tmp_path / ".omg" / "state"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(
            json.dumps({"run_id": "test-run-001"}),
            encoding="utf-8",
        )

        result = check_completion_claim_validity(str(tmp_path))

        assert result["allowed"] is False
        assert "proof gate verdict" in result["missing"]
        assert result["conclusion"] in ("uncertain", "failed")

    def test_active_session_failing_proof_blocks_completion(self, tmp_path: Path) -> None:
        """Active session with failing proof verdict blocks completion."""
        session_dir = tmp_path / ".omg" / "state"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(
            json.dumps({"run_id": "test-run-002"}),
            encoding="utf-8",
        )

        proof_dir = session_dir / "proof_gate"
        proof_dir.mkdir(parents=True)
        (proof_dir / "test-run-002.json").write_text(
            json.dumps({"verdict": "fail", "blockers": ["missing_tests"]}),
            encoding="utf-8",
        )

        result = check_completion_claim_validity(str(tmp_path))

        assert result["allowed"] is False
        assert "proof gate verdict" in result["missing"]


class TestCheckCompletionClaimValidityActiveSessionWithProof:
    """Test check_completion_claim_validity with active session + passing proof."""

    def test_active_session_passing_proof_allows_completion(self, tmp_path: Path) -> None:
        """Active session with passing proof gate verdict allows completion."""
        session_dir = tmp_path / ".omg" / "state"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(
            json.dumps({"run_id": "test-run-003"}),
            encoding="utf-8",
        )

        proof_dir = session_dir / "proof_gate"
        proof_dir.mkdir(parents=True)
        (proof_dir / "test-run-003.json").write_text(
            json.dumps({"verdict": "pass", "blockers": []}),
            encoding="utf-8",
        )

        # Add evidence bundle
        evidence_dir = tmp_path / ".omg" / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "test-run-003.json").write_text(
            json.dumps({"schema": "EvidencePack", "run_id": "test-run-003"}),
            encoding="utf-8",
        )

        result = check_completion_claim_validity(str(tmp_path))

        assert result["allowed"] is True
        assert result["missing"] == []
        assert result["conclusion"] == "verified"

    def test_passing_proof_without_evidence_is_inferred(self, tmp_path: Path) -> None:
        """Passing proof without evidence bundle gives inferred conclusion."""
        session_dir = tmp_path / ".omg" / "state"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(
            json.dumps({"run_id": "test-run-004"}),
            encoding="utf-8",
        )

        proof_dir = session_dir / "proof_gate"
        proof_dir.mkdir(parents=True)
        (proof_dir / "test-run-004.json").write_text(
            json.dumps({"verdict": "pass", "blockers": []}),
            encoding="utf-8",
        )

        result = check_completion_claim_validity(str(tmp_path))

        assert result["allowed"] is True
        assert result["conclusion"] == "inferred"
        assert "evidence bundle" in result["missing"]
        assert "advisory" in result
        assert "Evidence bundle missing" in result["advisory"]
        assert "verification commands" in result["advisory"]


class TestNarrateMissingEvidence:
    """Test narrate_missing_evidence function."""

    def test_empty_missing_list(self) -> None:
        """Empty missing list returns positive message."""
        result = narrate_missing_evidence([])
        assert "all required evidence is present" in result.lower()

    def test_single_missing_item(self) -> None:
        """Single missing item is narrated correctly."""
        result = narrate_missing_evidence(["test results"])

        assert "cannot confirm" in result.lower()
        assert "done" in result.lower()
        assert "test results" in result

    def test_multiple_missing_items(self) -> None:
        """Multiple missing items are joined with commas."""
        result = narrate_missing_evidence(["test results", "proof gate verdict"])

        assert "test results" in result
        assert "proof gate verdict" in result
        assert ", " in result

    def test_preserves_item_names(self) -> None:
        """Missing item names are preserved exactly."""
        items = ["junit.xml", "coverage report", "security scan"]
        result = narrate_missing_evidence(items)

        for item in items:
            assert item in result


class TestCompletionClaimPatterns:
    """Test COMPLETION_CLAIM_PATTERNS match expected keywords."""

    @pytest.mark.parametrize(
        "text,should_match",
        [
            ("done", True),
            ("DONE", True),
            ("Done.", True),
            ("fixed", True),
            ("Fixed the bug", True),
            ("works", True),
            ("It works now", True),
            ("ready", True),
            ("Ready for review", True),
            ("shipped", True),
            ("completed", True),
            ("lgtm", True),
            ("LGTM!", True),
            ("tests pass", True),
            ("tests passed", True),
            ("test passing", True),
            ("all tests green", True),
            # Should not match
            ("working on it", False),  # "working" != "works"
            ("undone", False),  # word boundary
            ("readiness check", False),  # word boundary
            ("let me check", False),
            ("still debugging", False),
        ],
    )
    def test_pattern_matches(self, text: str, should_match: bool) -> None:
        """Test that patterns correctly identify completion claims."""
        result = matches_completion_claim(text)
        assert result is should_match, f"Expected {should_match} for '{text}'"

    def test_patterns_are_case_insensitive(self) -> None:
        """All patterns should be case insensitive."""
        test_cases = ["DONE", "done", "Done", "DoNe"]
        for text in test_cases:
            assert matches_completion_claim(text), f"Should match: {text}"

    def test_patterns_are_valid_regex(self) -> None:
        """All patterns in COMPLETION_CLAIM_PATTERNS are valid regex."""
        for pattern in COMPLETION_CLAIM_PATTERNS:
            # Should not raise
            compiled = re.compile(pattern, re.IGNORECASE)
            assert compiled is not None


class TestCompletionClaimPatternsStructure:
    """Test COMPLETION_CLAIM_PATTERNS structure and completeness."""

    def test_patterns_is_list(self) -> None:
        """COMPLETION_CLAIM_PATTERNS is a list."""
        assert isinstance(COMPLETION_CLAIM_PATTERNS, list)

    def test_patterns_not_empty(self) -> None:
        """COMPLETION_CLAIM_PATTERNS has at least one pattern."""
        assert len(COMPLETION_CLAIM_PATTERNS) >= 1

    def test_patterns_are_strings(self) -> None:
        """All patterns are strings."""
        for pattern in COMPLETION_CLAIM_PATTERNS:
            assert isinstance(pattern, str)

    def test_patterns_cover_common_completion_words(self) -> None:
        """Patterns cover common completion claim words."""
        required_words = ["done", "fixed", "works", "ready", "lgtm"]
        for word in required_words:
            assert matches_completion_claim(word), f"Missing coverage for: {word}"
