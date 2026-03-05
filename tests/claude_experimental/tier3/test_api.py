"""Tests for claude_experimental.patterns.api — pattern_detect/validate/synthesize."""
from __future__ import annotations

import pytest

from claude_experimental.patterns.api import (
    PatternReport,
    SynthesisResult,
    ValidationReport,
    pattern_detect,
    pattern_synthesize,
    pattern_validate,
)
from claude_experimental.patterns.extractor import ASTExtractor


@pytest.mark.experimental
class TestPatternDetect:
    """pattern_detect: mine patterns from path with anti-pattern enrichment."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PATTERN_INTELLIGENCE")

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        ASTExtractor._cache.clear()
        yield
        ASTExtractor._cache.clear()

    def test_returns_pattern_report(self, tmp_path):
        """pattern_detect returns PatternReport with patterns and frequencies."""
        src = tmp_path / "mod.py"
        src.write_text(
            "import os\n"
            "import sys\n"
            "\n"
            "def hello():\n"
            "    return 'world'\n"
        )
        report = pattern_detect(str(tmp_path), min_support=0.1)

        assert isinstance(report, PatternReport)
        assert report.total_files >= 1
        assert isinstance(report.frequencies, dict)
        assert isinstance(report.baseline, dict)

    def test_detects_antipatterns_in_frequencies(self, tmp_path):
        """pattern_detect enriches report with antipattern:* keys."""
        src = tmp_path / "bad.py"
        src.write_text(
            "def broken(items=[]):\n"
            "    try:\n"
            "        pass\n"
            "    except:\n"
            "        pass\n"
        )
        report = pattern_detect(str(tmp_path))

        anti_keys = [k for k in report.frequencies if k.startswith("antipattern:")]
        assert len(anti_keys) > 0
        assert "anti_pattern_total" in report.baseline


@pytest.mark.experimental
class TestPatternValidate:
    """pattern_validate: check support of a candidate pattern against a codebase."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PATTERN_INTELLIGENCE")

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        ASTExtractor._cache.clear()
        yield
        ASTExtractor._cache.clear()

    def test_returns_validation_report(self, tmp_path):
        """pattern_validate returns ValidationReport with support metric."""
        src = tmp_path / "a.py"
        src.write_text("import os\nimport sys\n\ndef foo():\n    pass\n")

        result = pattern_validate("import os", against_path=str(tmp_path))

        assert isinstance(result, ValidationReport)
        assert isinstance(result.support, float)
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.violations, list)
        assert isinstance(result.confidence, float)

    def test_validate_with_pattern_object(self, tmp_path):
        """pattern_validate accepts Pattern object as candidate."""
        from claude_experimental.patterns.extractor import Pattern

        src = tmp_path / "b.py"
        src.write_text("import json\nimport os\n\ndef bar():\n    pass\n")

        candidate = Pattern(
            type="import", name="json", frequency=1,
            location="test:1", snippet="import json"
        )
        result = pattern_validate(candidate, against_path=str(tmp_path))

        assert isinstance(result, ValidationReport)
        assert result.pattern  # non-empty pattern identifier


@pytest.mark.experimental
class TestPatternSynthesize:
    """pattern_synthesize: template-based pattern synthesis."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PATTERN_INTELLIGENCE")

    def test_synthesize_basic(self):
        """Synthesis returns SynthesisResult with suggestions."""
        result = pattern_synthesize("def handler(request):")

        assert isinstance(result, SynthesisResult)
        assert result.template == "def handler(request):"
        assert len(result.suggestions) >= 2
        assert result.confidence > 0.0

    def test_synthesize_with_constraints(self):
        """Constraints increase confidence and appear in suggestions."""
        result = pattern_synthesize(
            "class Service:",
            constraints={"pattern": "singleton", "thread_safe": True},
        )

        assert isinstance(result, SynthesisResult)
        assert result.confidence == 0.9  # constrained = 0.9
        assert any("singleton" in s for s in result.suggestions)
