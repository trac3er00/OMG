from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from claude_experimental.parallel.api import (
    AggregatedValue,
    AggregationMode,
    IndividualResult,
    ParallelResult,
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def calculate_quality_score(result: IndividualResult) -> float:
    exit_ok = 1.0 if result.exit_code == 0 else 0.0
    length_score = min(len(result.content) / 1000.0, 1.0)
    time_score = max(0.0, 1.0 - (result.duration_ms / 30000.0))
    lowered = result.content.lower()
    has_error = "error" in lowered or "traceback" in lowered
    no_error = 0.0 if has_error else 1.0

    score = (exit_ok * 0.4) + (length_score * 0.2) + (time_score * 0.2) + (no_error * 0.2)
    return _clamp(score, 0.0, 1.0)


@dataclass(frozen=True)
class ScoredResult:
    result: IndividualResult
    quality_score: float


class AggregationStrategy(Protocol):
    name: str

    def aggregate(self, scored_results: list[ScoredResult]) -> AggregatedValue:
        ...


class BestResultStrategy:
    name: str = AggregationMode.BEST_RESULT.value

    def aggregate(self, scored_results: list[ScoredResult]) -> AggregatedValue:
        if not scored_results:
            return None
        best = max(scored_results, key=lambda item: item.quality_score)
        return best.result.content


class AllResultsStrategy:
    name: str = AggregationMode.ALL_RESULTS.value

    def aggregate(self, scored_results: list[ScoredResult]) -> AggregatedValue:
        ordered = sorted(scored_results, key=lambda item: item.quality_score, reverse=True)
        return [item.result.content for item in ordered]


class FirstSuccessStrategy:
    name: str = AggregationMode.FIRST_SUCCESS.value

    def aggregate(self, scored_results: list[ScoredResult]) -> AggregatedValue:
        for item in scored_results:
            if item.result.exit_code == 0:
                return item.result.content
        return None


class ResultAggregator:

    def __init__(self, strategy: AggregationStrategy):
        self._strategy: AggregationStrategy = strategy

    def aggregate(self, results: list[IndividualResult]) -> ParallelResult:
        scored_results = [
            ScoredResult(result=result, quality_score=calculate_quality_score(result))
            for result in results
        ]
        aggregated = self._strategy.aggregate(scored_results)
        succeeded = sum(1 for result in results if result.exit_code == 0)
        failed = len(results) - succeeded

        ranked = sorted(scored_results, key=lambda item: item.quality_score, reverse=True)
        quality_ranking = [
            f"{item.result.recipient}:{item.quality_score:.3f}"
            for item in ranked
        ]

        return ParallelResult(
            results=results,
            aggregated=aggregated,
            execution_summary={
                "aggregation": self._strategy.name,
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "quality_ranking": quality_ranking,
            },
            partial=failed > 0,
        )


def strategy_for_mode(mode: AggregationMode | str) -> AggregationStrategy:
    normalized = mode if isinstance(mode, AggregationMode) else AggregationMode(str(mode).upper())
    if normalized is AggregationMode.ALL_RESULTS:
        return AllResultsStrategy()
    if normalized is AggregationMode.FIRST_SUCCESS:
        return FirstSuccessStrategy()
    return BestResultStrategy()


def aggregate_results(
    results: list[IndividualResult],
    mode: AggregationMode | str,
) -> ParallelResult:
    return ResultAggregator(strategy_for_mode(mode)).aggregate(results)


__all__ = [
    "AggregationStrategy",
    "AllResultsStrategy",
    "BestResultStrategy",
    "FirstSuccessStrategy",
    "ResultAggregator",
    "ScoredResult",
    "aggregate_results",
    "calculate_quality_score",
    "strategy_for_mode",
]
