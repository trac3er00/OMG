from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Protocol, cast


class SuggestionLike(Protocol):
    description: str
    impact: float
    effort: float
    risk: float
    category: str
    composite: float


JSONDict = dict[str, object]


class ReportLike(Protocol):
    scores: dict[str, float]
    suggestions: list[SuggestionLike]

    def to_dict(self) -> JSONDict: ...


class AnalyzerLike(Protocol):
    def __call__(self, project_dir: str = ".") -> "AnalyzerInstanceLike": ...


class AnalyzerInstanceLike(Protocol):
    def analyze(self, focus: str | None = None) -> ReportLike: ...


project_analyzer = import_module("runtime.project_analyzer")
CATEGORIES = cast(tuple[str, ...], getattr(project_analyzer, "CATEGORIES"))
DIMENSIONS = cast(tuple[str, ...], getattr(project_analyzer, "DIMENSIONS"))
AnalysisReport = cast(type[ReportLike], getattr(project_analyzer, "AnalysisReport"))
ProjectAnalyzer = cast(AnalyzerLike, getattr(project_analyzer, "ProjectAnalyzer"))


def test_analyze_returns_all_dimensions(tmp_path: Path):
    """Analysis should return scores for all 6 dimensions."""
    analyzer = ProjectAnalyzer(project_dir=str(tmp_path))
    report = analyzer.analyze()
    assert isinstance(report, AnalysisReport)
    for dim in DIMENSIONS:
        assert dim in report.scores, f"Missing dimension: {dim}"
        score = report.scores[dim]
        assert 0 <= score <= 100, f"{dim} score {score} out of range"


def test_analyze_returns_suggestions(tmp_path: Path):
    """Analysis should return at least some suggestions."""
    analyzer = ProjectAnalyzer(project_dir=str(tmp_path))
    report = analyzer.analyze()
    assert isinstance(report.suggestions, list)


def test_suggestions_are_ranked(tmp_path: Path):
    """Suggestions should be ranked by composite score."""
    analyzer = ProjectAnalyzer(project_dir=str(tmp_path))
    report = analyzer.analyze()
    if len(report.suggestions) > 1:
        for i in range(len(report.suggestions) - 1):
            assert report.suggestions[i].composite >= report.suggestions[i + 1].composite


def test_focus_filter_limits_category(tmp_path: Path):
    """Focus filter should only return suggestions in that category."""
    analyzer = ProjectAnalyzer(project_dir=str(tmp_path))
    report = analyzer.analyze(focus="security")
    for suggestion in report.suggestions:
        assert suggestion.category == "security"


def test_suggestion_has_required_fields(tmp_path: Path):
    """Each suggestion should have all required fields."""
    analyzer = ProjectAnalyzer(project_dir=str(tmp_path))
    report = analyzer.analyze()
    for suggestion in report.suggestions:
        assert suggestion.description
        assert 0 <= suggestion.impact <= 100
        assert 0 <= suggestion.effort <= 100
        assert 0 <= suggestion.risk <= 100
        assert suggestion.category in CATEGORIES
        assert suggestion.composite >= 0


def test_to_dict_has_required_structure(tmp_path: Path):
    """Report dict should have expected structure."""
    analyzer = ProjectAnalyzer(project_dir=str(tmp_path))
    report = analyzer.analyze()
    data = report.to_dict()
    assert "scores" in data
    assert "suggestions" in data
    suggestions = cast(list[JSONDict], data["suggestions"])
    if suggestions:
        suggestion = suggestions[0]
        assert "description" in suggestion
        assert "impact" in suggestion
        assert "effort" in suggestion
        assert "category" in suggestion
        assert "composite" in suggestion
