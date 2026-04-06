from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from typing import Protocol, cast

module_path = (
    Path(__file__).resolve().parents[2] / "runtime" / "complexity_classifier.py"
)
module_spec = spec_from_file_location("runtime.complexity_classifier", module_path)
assert module_spec is not None
assert module_spec.loader is not None
complexity_classifier = module_from_spec(module_spec)
sys.modules[module_spec.name] = complexity_classifier
module_spec.loader.exec_module(complexity_classifier)

classify = cast(
    Callable[..., object],
    getattr(complexity_classifier, "classify"),
)
ComplexityResult = cast(
    type[object], getattr(complexity_classifier, "ComplexityResult")
)
COMPLEXITY_TIERS = cast(
    Sequence[str], getattr(complexity_classifier, "COMPLEXITY_TIERS")
)


class _ComplexityResultLike(Protocol):
    tier: str
    confidence: float
    reasoning: str
    scores: dict[str, float]


def _classify(
    task: Mapping[str, object],
    overrides: Mapping[str, str] | None = None,
) -> _ComplexityResultLike:
    return cast(_ComplexityResultLike, classify(task, overrides=overrides))


def test_single_file_fix_is_trivial() -> None:
    result = _classify({"files": 1, "lines_changed": 2, "type": "fix"})
    assert result.tier == "trivial"
    assert result.confidence > 0.7
    assert 0.0 <= result.confidence <= 1.0


def test_multi_module_refactor_is_complex() -> None:
    result = _classify(
        {
            "files": 12,
            "modules": 4,
            "cross_cutting": True,
            "type": "refactor",
            "lines_changed": 400,
        }
    )
    assert result.tier in ("complex", "critical")
    assert result.confidence > 0.7


def test_security_fix_escalates_complexity() -> None:
    result = _classify(
        {
            "files": 2,
            "risk_indicators": ["security", "auth"],
            "type": "fix",
            "lines_changed": 30,
        }
    )
    assert result.tier != "trivial"


def test_tier_override() -> None:
    result = _classify({"files": 1}, overrides={"tier": "critical"})
    assert result.tier == "critical"
    assert result.confidence == 1.0


def test_all_tiers_reachable() -> None:
    trivial = _classify({"files": 1, "lines_changed": 2, "type": "docs"})
    assert trivial.tier == "trivial"

    complex_ = _classify(
        {
            "files": 15,
            "lines_changed": 600,
            "cross_cutting": True,
            "modules": 5,
            "type": "refactor",
        }
    )
    assert complex_.tier in ("complex", "critical")


def test_confidence_in_range() -> None:
    for files in [1, 5, 20]:
        result = _classify({"files": files, "lines_changed": files * 10})
        assert 0.0 <= result.confidence <= 1.0


def test_result_has_all_fields() -> None:
    result = _classify({"files": 3, "lines_changed": 50})
    assert isinstance(result, ComplexityResult)
    assert result.tier in COMPLEXITY_TIERS
    assert isinstance(result.reasoning, str)
    assert isinstance(result.scores, dict)


def test_empty_task_defaults_to_trivial() -> None:
    result = _classify({})
    assert result.tier == "trivial"
