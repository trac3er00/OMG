from __future__ import annotations

from collections.abc import Mapping
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .antipatterns import (
    AntiPatternDetector,
    AntiPatternViolation,
)
from .extractor import Pattern
from .mining import PatternMiner, PatternReport


@dataclass(frozen=True)
class ValidationReport:
    pattern: str
    support: float
    is_valid: bool
    violations: list[str]
    confidence: float


@dataclass(frozen=True)
class SynthesisResult:
    template: str
    suggestions: list[str]
    confidence: float


def pattern_detect(
    path: str,
    min_support: float = 0.05,
    pattern_type: str = "sequential",
) -> PatternReport:
    _require_patterns_enabled()

    miner = PatternMiner()
    mined_report = miner.mine(path, min_support=min_support, pattern_type=pattern_type)
    anti_violations = _detect_anti_patterns(path)

    anti_counts = Counter(v.rule_name for v in anti_violations)
    anti_frequencies = {f"antipattern:{rule}": count for rule, count in anti_counts.items()}

    total_files = mined_report.total_files
    anti_deviations = {
        key: (float(value) / float(total_files) if total_files > 0 else 0.0)
        for key, value in anti_frequencies.items()
    }

    baseline = dict(mined_report.baseline)
    baseline["anti_pattern_total"] = float(len(anti_violations))
    baseline["anti_pattern_unique_rules"] = float(len(anti_counts))

    return PatternReport(
        patterns=mined_report.patterns,
        frequencies={**mined_report.frequencies, **anti_frequencies},
        deviations={**mined_report.deviations, **anti_deviations},
        baseline=baseline,
        total_files=mined_report.total_files,
    )


def pattern_validate(
    candidate_pattern: Pattern | Mapping[str, object] | str,
    against_path: str,
    min_support: float = 0.05,
) -> ValidationReport:
    _require_patterns_enabled()

    pattern_type, pattern_name = _normalize_candidate_pattern(candidate_pattern)

    miner = PatternMiner()
    if pattern_type in {"sequential", "structural"}:
        reports = [miner.mine(against_path, min_support=0.0, pattern_type=pattern_type)]
    else:
        reports = [
            miner.mine(against_path, min_support=0.0, pattern_type="sequential"),
            miner.mine(against_path, min_support=0.0, pattern_type="structural"),
        ]

    total_files = max((report.total_files for report in reports), default=0)
    target_key = f"{pattern_type}:{pattern_name}" if pattern_type else pattern_name

    frequency = 0
    for report in reports:
        if target_key in report.frequencies:
            frequency = report.frequencies[target_key]
            break
        if not pattern_type:
            for key, value in report.frequencies.items():
                if key.endswith(f":{pattern_name}"):
                    frequency = value
                    target_key = key
                    break

    support = float(frequency) / float(total_files) if total_files > 0 else 0.0
    is_valid = support >= min_support

    anti_violations = _detect_anti_patterns(against_path)
    violation_lines = [
        f"{item.rule_name}@{item.line} [{item.severity}]"
        for item in anti_violations
    ]
    penalty = min(0.5, len(anti_violations) * 0.02)
    confidence = max(0.0, min(1.0, support + (0.1 if is_valid else 0.0) - penalty))

    return ValidationReport(
        pattern=target_key,
        support=support,
        is_valid=is_valid,
        violations=violation_lines,
        confidence=confidence,
    )


def pattern_synthesize(template: str, constraints: Mapping[str, object] | None = None) -> SynthesisResult:
    _require_patterns_enabled()

    normalized_constraints = constraints or {}
    suggestions = [template]

    if normalized_constraints:
        flat_constraints = ", ".join(
            f"{name}={value}" for name, value in sorted(normalized_constraints.items())
        )
        suggestions.append(f"{template} [{flat_constraints}]")
        suggestions.append(f"{template} // constrained by {flat_constraints}")
    else:
        suggestions.append(f"{template} // baseline variation")
        suggestions.append(f"{template} // strict variation")

    confidence = 0.9 if normalized_constraints else 0.7
    return SynthesisResult(template=template, suggestions=suggestions, confidence=confidence)


def _normalize_candidate_pattern(candidate_pattern: Pattern | Mapping[str, object] | str) -> tuple[str, str]:
    if isinstance(candidate_pattern, Pattern):
        return candidate_pattern.type, candidate_pattern.name

    if isinstance(candidate_pattern, dict):
        pattern_type = str(candidate_pattern.get("type", "")).strip()
        pattern_name = str(candidate_pattern.get("name", "")).strip()
        if pattern_name:
            return pattern_type, pattern_name

    if isinstance(candidate_pattern, str):
        value = candidate_pattern.strip()
        if not value:
            return "", ""
        if ":" in value:
            pattern_type, pattern_name = value.split(":", 1)
            return pattern_type.strip(), pattern_name.strip()
        return "", value

    return "", str(candidate_pattern)


def _require_patterns_enabled() -> None:
    import claude_experimental.patterns as patterns

    getattr(patterns, "_require_enabled")()


def _detect_anti_patterns(path: str) -> list[AntiPatternViolation]:
    detector = AntiPatternDetector()
    violations: list[AntiPatternViolation] = []
    for file_path in _discover_python_files(path):
        try:
            violations.extend(detector.detect(str(file_path)))
        except Exception:
            continue
    return violations


def _discover_python_files(path: str) -> list[Path]:
    root = Path(path)
    if root.is_file() and root.suffix == ".py":
        return [root]
    if not root.exists():
        return []

    files = [file_path for file_path in root.rglob("*.py") if file_path.is_file()]
    files.sort()
    return files


__all__ = [
    "PatternReport",
    "ValidationReport",
    "SynthesisResult",
    "pattern_detect",
    "pattern_validate",
    "pattern_synthesize",
]
