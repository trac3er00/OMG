"""Project analysis engine for /next command.

Analyzes: code quality, test coverage, security, dependency health,
documentation completeness, and architecture.

Generates improvement suggestions ranked by: impact × (100-effort) × (100-risk).
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast


JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict = dict[str, object]


class FindingLike(Protocol):
    severity: str


class ReportLike(Protocol):
    findings: list[FindingLike]


class ReviewerLike(Protocol):
    def scan(self, scope: str | Path = ".") -> ReportLike: ...


class ReviewerFactory(Protocol):
    def __call__(self, severity_floor: str = "medium") -> ReviewerLike: ...


DIMENSIONS = (
    "code_quality",
    "test_coverage",
    "security",
    "dependency_health",
    "documentation",
    "architecture",
)
CATEGORIES = (
    "security",
    "performance",
    "maintainability",
    "testing",
    "documentation",
    "architecture",
)


@dataclass
class DimensionScore:
    name: str
    score: float  # 0-100
    issues: list[str] = field(default_factory=list)


@dataclass
class Suggestion:
    description: str
    impact: float  # 0-100
    effort: float  # 0-100 (higher = more effort)
    risk: float  # 0-100 (higher = more risk)
    category: str
    composite: float = 0.0

    def __post_init__(self) -> None:
        self.composite = (
            (self.impact / 100)
            * ((100 - self.effort) / 100)
            * ((100 - self.risk) / 100)
            * 100
        )


@dataclass
class AnalysisReport:
    scores: dict[str, float] = field(default_factory=dict)
    suggestions: list[Suggestion] = field(default_factory=list)
    cached_at: float = 0.0

    def to_dict(self) -> JSONDict:
        return {
            "scores": self.scores,
            "suggestions": [
                {
                    "description": suggestion.description,
                    "impact": suggestion.impact,
                    "effort": suggestion.effort,
                    "risk": suggestion.risk,
                    "category": suggestion.category,
                    "composite": round(suggestion.composite, 1),
                }
                for suggestion in self.suggestions
            ],
            "cached_at": self.cached_at,
        }


def _run_cmd(cmd: list[str], cwd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "", "", 1
    return result.stdout, result.stderr, result.returncode


def _score_code_quality(project_dir: str) -> DimensionScore:
    """Score code quality using ruff and basic heuristics."""
    issues: list[str] = []
    score = 80.0
    stdout, _, rc = _run_cmd(
        [
            "python3",
            "-m",
            "ruff",
            "check",
            ".",
            "--select",
            "E,W,F",
            "--statistics",
        ],
        project_dir,
        timeout=20,
    )
    if rc == 0:
        score = 90.0
    elif stdout:
        lines = [line for line in stdout.splitlines() if line.strip() and not line.startswith("Found")]
        issue_count = len(lines)
        score = max(20.0, 90.0 - min(70.0, issue_count * 2))
        if issue_count > 0:
            issues.append(f"{issue_count} lint issues found")
    return DimensionScore(name="code_quality", score=round(score), issues=issues)


def _score_test_coverage(project_dir: str) -> DimensionScore:
    """Score test coverage by comparing source and test file counts."""
    issues: list[str] = []
    project_path = Path(project_dir)

    py_source = [
        path
        for path in project_path.rglob("*.py")
        if "test" not in path.name and "__pycache__" not in str(path)
    ]
    py_tests = list(project_path.rglob("test_*.py"))
    ts_source = [
        path
        for path in project_path.rglob("*.ts")
        if "test" not in path.name and "node_modules" not in str(path)
    ]
    ts_tests = list(project_path.rglob("*.test.ts"))

    source_total = len(py_source) + len(ts_source)
    test_total = len(py_tests) + len(ts_tests)

    if source_total == 0:
        return DimensionScore(name="test_coverage", score=50.0, issues=issues)

    ratio = test_total / source_total
    score = min(95.0, ratio * 100)
    if score < 50:
        issues.append(f"Low test coverage: {test_total} tests for {source_total} source files")
    return DimensionScore(name="test_coverage", score=round(score), issues=issues)


def _score_security(project_dir: str) -> DimensionScore:
    """Score security posture using the adversarial review engine when available."""
    issues: list[str] = []
    try:
        adversarial_review = import_module("runtime.adversarial_review")
        AdversarialReview = cast(
            ReviewerFactory,
            getattr(adversarial_review, "AdversarialReview"),
        )
        review = AdversarialReview(severity_floor="medium")
        report = review.scan(project_dir)
        critical = sum(
            1 for finding in report.findings if finding.severity in ("critical", "high")
        )
        medium = sum(1 for finding in report.findings if finding.severity == "medium")
        if critical == 0 and medium == 0:
            score = 90.0
        elif critical == 0:
            score = max(50.0, 80.0 - medium * 5)
        else:
            score = max(10.0, 60.0 - critical * 15)
            issues.append(f"{critical} critical/high security issues found")
    except Exception:
        score = 70.0
    return DimensionScore(name="security", score=round(score), issues=issues)


def _score_documentation(project_dir: str) -> DimensionScore:
    """Score documentation completeness."""
    issues: list[str] = []
    project_path = Path(project_dir)
    checks = {
        "README.md": project_path / "README.md",
        "docs/GETTING-STARTED.md": project_path / "docs" / "GETTING-STARTED.md",
        "CHANGELOG.md": project_path / "CHANGELOG.md",
        "CONTRIBUTING.md": project_path / "CONTRIBUTING.md",
    }
    present = sum(1 for path in checks.values() if path.exists())
    score = (present / len(checks)) * 100
    missing = [name for name, path in checks.items() if not path.exists()]
    if missing:
        issues.append(f"Missing docs: {', '.join(missing[:3])}")
    return DimensionScore(name="documentation", score=round(score), issues=issues)


def _json_int(value: JSONValue) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return 0


def _score_dependency_health(project_dir: str) -> DimensionScore:
    """Score dependency health using npm audit when available."""
    issues: list[str] = []
    score = 75.0
    stdout, _, rc = _run_cmd(["npm", "audit", "--json"], project_dir, timeout=30)
    if rc == 0 and stdout:
        try:
            data = cast(dict[str, JSONValue], json.loads(stdout))
            metadata = cast(dict[str, JSONValue], data.get("metadata", {}))
            vulnerabilities = cast(dict[str, JSONValue], metadata.get("vulnerabilities", {}))
            critical = _json_int(vulnerabilities.get("critical", 0)) + _json_int(
                vulnerabilities.get("high", 0)
            )
            if critical == 0:
                score = 85.0
            else:
                score = max(30.0, 80.0 - critical * 10)
                issues.append(f"{critical} critical/high npm vulnerabilities")
        except Exception:
            pass
    return DimensionScore(name="dependency_health", score=round(score), issues=issues)


def _score_architecture(project_dir: str) -> DimensionScore:
    """Score architecture quality."""
    issues: list[str] = []
    boundaries_doc = Path(project_dir) / "docs" / "architecture" / "core-pack-boundaries.md"
    if boundaries_doc.exists():
        score = 80.0
    else:
        score = 50.0
        issues.append("No architecture documentation")
    return DimensionScore(name="architecture", score=round(score), issues=issues)


def _generate_suggestions(scores: dict[str, DimensionScore]) -> list[Suggestion]:
    """Generate improvement suggestions based on score thresholds."""
    suggestions: list[Suggestion] = []
    for name, dimension in scores.items():
        score = dimension.score
        if name == "security" and score < 70:
            suggestions.append(
                Suggestion(
                    description="Fix security vulnerabilities: run /red-team to identify and fix issues",
                    impact=90,
                    effort=40,
                    risk=20,
                    category="security",
                )
            )
        elif name == "test_coverage" and score < 60:
            suggestions.append(
                Suggestion(
                    description="Increase test coverage: add unit tests for untested modules",
                    impact=70,
                    effort=50,
                    risk=10,
                    category="testing",
                )
            )
        elif name == "code_quality" and score < 70:
            suggestions.append(
                Suggestion(
                    description="Fix code quality issues: run ruff and address lint errors",
                    impact=50,
                    effort=30,
                    risk=5,
                    category="maintainability",
                )
            )
        elif name == "documentation" and score < 60:
            suggestions.append(
                Suggestion(
                    description="Improve documentation: add missing guides and README sections",
                    impact=40,
                    effort=20,
                    risk=5,
                    category="documentation",
                )
            )
        elif name == "dependency_health" and score < 60:
            suggestions.append(
                Suggestion(
                    description="Update vulnerable dependencies: run npm audit fix",
                    impact=60,
                    effort=20,
                    risk=30,
                    category="security",
                )
            )
        elif name == "architecture" and score < 60:
            suggestions.append(
                Suggestion(
                    description="Document architecture: create core/pack boundaries and module map",
                    impact=50,
                    effort=30,
                    risk=5,
                    category="architecture",
                )
            )
    suggestions.sort(key=lambda suggestion: suggestion.composite, reverse=True)
    return suggestions


class ProjectAnalyzer:
    """Multi-dimensional project analyzer."""

    def __init__(self, project_dir: str = "."):
        self.project_dir: str = project_dir
        self._cache: AnalysisReport | None = None
        self._cache_ttl: int = 300

    def analyze(self, focus: str | None = None) -> AnalysisReport:
        """Run project analysis and optionally filter suggestions by category."""
        if self._cache and (time.time() - self._cache.cached_at) < self._cache_ttl:
            report = self._cache
        else:
            scores = {
                "code_quality": _score_code_quality(self.project_dir),
                "test_coverage": _score_test_coverage(self.project_dir),
                "security": _score_security(self.project_dir),
                "dependency_health": _score_dependency_health(self.project_dir),
                "documentation": _score_documentation(self.project_dir),
                "architecture": _score_architecture(self.project_dir),
            }
            report = AnalysisReport(
                scores={name: dimension.score for name, dimension in scores.items()},
                suggestions=_generate_suggestions(scores),
                cached_at=time.time(),
            )
            self._cache = report

        if focus and focus != "all":
            return AnalysisReport(
                scores=report.scores,
                suggestions=[suggestion for suggestion in report.suggestions if suggestion.category == focus],
                cached_at=report.cached_at,
            )
        return report
