"""Tests for claude_experimental.patterns.refactoring — RefactoringSuggester."""
from __future__ import annotations

import pytest

from claude_experimental.patterns.extractor import ASTExtractor
from claude_experimental.patterns.refactoring import (
    RefactoringSuggester,
    RefactoringSuggestionReport,
)


@pytest.mark.experimental
class TestRefactoringSuggester:
    """RefactoringSuggester: maps anti-patterns to actionable refactoring suggestions."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PATTERN_INTELLIGENCE")

    def test_suggest_deep_nesting(self, tmp_path):
        """Deeply nested code produces 'extract' / nesting-related suggestions."""
        src = tmp_path / "nested.py"
        src.write_text(
            "def process():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                if True:\n"
            "                    if True:\n"
            "                        result = 42\n"
        )
        suggester = RefactoringSuggester()
        report = suggester.suggest(str(src))

        assert isinstance(report, RefactoringSuggestionReport)
        nesting_suggestions = [
            s for s in report.suggestions if s.rule_name == "deep_nesting"
        ]
        assert len(nesting_suggestions) >= 1
        assert any(
            "extract" in s.transformation.lower() or "nesting" in s.description.lower()
            for s in nesting_suggestions
        )

    def test_suggest_clean_file_no_suggestions(self, tmp_path):
        """Clean file produces no suggestions and high score."""
        src = tmp_path / "pristine.py"
        src.write_text(
            "\"\"\"Clean module.\"\"\"\n"
            "\n"
            "\n"
            "def add(a: int, b: int) -> int:\n"
            "    \"\"\"Add two integers.\"\"\"\n"
            "    return a + b\n"
        )
        suggester = RefactoringSuggester()
        report = suggester.suggest(str(src))

        assert len(report.suggestions) == 0
        assert report.total_score > 0.9
        assert "No refactoring suggestions" in report.summary

    def test_suggest_multiple_issues(self, tmp_path):
        """File with multiple anti-patterns gets multiple prioritized suggestions."""
        src = tmp_path / "multi.py"
        src.write_text(
            "def bad(items=[]):\n"  # mutable default (high)
            "    try:\n"
            "        x = 1 / 0\n"
            "    except:\n"  # bare except (high)
            "        pass\n"  # empty except (high)
            "    print(items)\n"  # print statement (low)
        )
        suggester = RefactoringSuggester()
        report = suggester.suggest(str(src))

        assert len(report.suggestions) >= 3
        # Should be sorted by severity: critical/high before medium/low
        severities = [s.severity for s in report.suggestions]
        if "high" in severities and "low" in severities:
            first_high = severities.index("high")
            last_low = len(severities) - 1 - severities[::-1].index("low")
            assert first_high < last_low

    def test_summary_contains_file_path(self, tmp_path):
        """Report summary includes the file path."""
        src = tmp_path / "summary_test.py"
        src.write_text(
            "def ok():\n"
            "    try:\n"
            "        pass\n"
            "    except:\n"
            "        pass\n"
        )
        suggester = RefactoringSuggester()
        report = suggester.suggest(str(src))

        assert "summary_test.py" in report.summary
        assert "score" in report.summary.lower()

    def test_suggestions_have_effort_field(self, tmp_path):
        """Each suggestion has an effort estimate (low/medium/high)."""
        src = tmp_path / "effort.py"
        src.write_text(
            "def bad(items=[]):\n"
            "    return items\n"
        )
        suggester = RefactoringSuggester()
        report = suggester.suggest(str(src))

        for s in report.suggestions:
            assert s.effort in ("low", "medium", "high")
