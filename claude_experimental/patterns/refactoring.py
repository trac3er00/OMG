"""Automated refactoring suggestion engine for Python source files.

Maps anti-pattern violations to actionable refactoring suggestions with
effort estimates, enabling prioritized code improvement workflows.

Feature-flag gated: OMG_PATTERN_INTELLIGENCE_ENABLED=1
"""
from __future__ import annotations

from dataclasses import dataclass

from claude_experimental.patterns.antipatterns import (
    AntiPatternDetector,
    AntiPatternViolation,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RefactoringSuggestion:
    """A single refactoring suggestion derived from an anti-pattern violation."""

    rule_name: str
    severity: str  # critical | high | medium | low
    line: int
    description: str
    transformation: str
    effort: str  # low | medium | high


@dataclass
class RefactoringSuggestionReport:
    """Aggregated refactoring report for a single file."""

    file_path: str
    suggestions: list[RefactoringSuggestion]
    total_score: float  # 0.0–1.0 quality score from AntiPatternDetector
    summary: str


# ---------------------------------------------------------------------------
# Severity ordering for sorting (critical first)
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


# ---------------------------------------------------------------------------
# Violation → Suggestion mapping
# ---------------------------------------------------------------------------

_REFACTORING_MAP: dict[str, tuple[str, str]] = {
    # rule_name → (transformation description, effort)
    "bare_except": (
        "Replace bare except with specific exception type",
        "low",
    ),
    "mutable_default": (
        "Replace mutable default argument with None sentinel",
        "low",
    ),
    "god_class": (
        "Extract methods into separate classes or modules",
        "high",
    ),
    "deep_nesting": (
        "Extract nested logic into helper functions",
        "medium",
    ),
    "long_function": (
        "Extract function into smaller focused functions",
        "medium",
    ),
    "unused_import": (
        "Remove unused import",
        "low",
    ),
    "print_statement": (
        "Replace print() with logging module",
        "low",
    ),
    "empty_except": (
        "Add error handling or logging in except block",
        "low",
    ),
    "magic_number": (
        "Replace magic number with named constant",
        "low",
    ),
    "type_ignore_no_reason": (
        "Add type annotation instead of type: ignore",
        "medium",
    ),
}


# ---------------------------------------------------------------------------
# RefactoringSuggester
# ---------------------------------------------------------------------------


class RefactoringSuggester:
    """Analyzes Python files and produces prioritized refactoring suggestions.

    Uses ``AntiPatternDetector`` internally to detect violations and maps each
    violation to an actionable refactoring suggestion with effort estimates.

    Usage::

        suggester = RefactoringSuggester()
        report = suggester.suggest("path/to/module.py")
        for s in report.suggestions:
            print(f"[{s.severity}] L{s.line}: {s.transformation} (effort: {s.effort})")
    """

    def __init__(
        self, *, detector: AntiPatternDetector | None = None
    ) -> None:
        self._detector = (
            detector if detector is not None else AntiPatternDetector()
        )

    # -- public API --------------------------------------------------------

    def suggest(self, file_path: str) -> RefactoringSuggestionReport:
        """Analyze *file_path* and return a prioritized refactoring report.

        Raises ``RuntimeError`` if the ``PATTERN_INTELLIGENCE`` feature flag
        is not enabled.
        """
        from claude_experimental.patterns import _require_enabled

        _require_enabled()

        # Detect violations and compute quality score
        violations = self._detector.detect(file_path)
        total_score = self._detector.score(file_path)

        # Map violations to suggestions
        suggestions = self._map_violations(violations)

        # Sort by severity (critical first)
        suggestions.sort(key=lambda s: _SEVERITY_ORDER.get(s.severity, 99))

        # Generate summary
        summary = self._build_summary(file_path, suggestions, total_score)

        return RefactoringSuggestionReport(
            file_path=file_path,
            suggestions=suggestions,
            total_score=total_score,
            summary=summary,
        )

    # -- internal ----------------------------------------------------------

    def _map_violations(
        self, violations: list[AntiPatternViolation]
    ) -> list[RefactoringSuggestion]:
        """Convert anti-pattern violations into refactoring suggestions."""
        suggestions: list[RefactoringSuggestion] = []
        for v in violations:
            mapping = _REFACTORING_MAP.get(v.rule_name)
            if mapping is None:
                # Unknown rule: provide generic suggestion
                transformation = f"Review and address: {v.description}"
                effort = "medium"
            else:
                transformation, effort = mapping

            suggestions.append(
                RefactoringSuggestion(
                    rule_name=v.rule_name,
                    severity=v.severity,
                    line=v.line,
                    description=v.description,
                    transformation=transformation,
                    effort=effort,
                )
            )
        return suggestions

    @staticmethod
    def _build_summary(
        file_path: str,
        suggestions: list[RefactoringSuggestion],
        total_score: float,
    ) -> str:
        """Build a human-readable summary of the refactoring report."""
        if not suggestions:
            return (
                f"{file_path}: No refactoring suggestions "
                f"(score: {total_score:.2f})"
            )

        # Count by severity
        severity_counts: dict[str, int] = {}
        for s in suggestions:
            severity_counts[s.severity] = (
                severity_counts.get(s.severity, 0) + 1
            )

        # Count by effort
        effort_counts: dict[str, int] = {}
        for s in suggestions:
            effort_counts[s.effort] = effort_counts.get(s.effort, 0) + 1

        parts = [f"{file_path}: {len(suggestions)} suggestion(s)"]
        parts.append(f"quality score: {total_score:.2f}")

        severity_parts = []
        for sev in ("critical", "high", "medium", "low"):
            if sev in severity_counts:
                severity_parts.append(f"{severity_counts[sev]} {sev}")
        if severity_parts:
            parts.append(f"by severity: {', '.join(severity_parts)}")

        effort_parts = []
        for eff in ("low", "medium", "high"):
            if eff in effort_counts:
                effort_parts.append(f"{effort_counts[eff]} {eff}-effort")
        if effort_parts:
            parts.append(f"by effort: {', '.join(effort_parts)}")

        return "; ".join(parts)
