"""Tests for ResultAggregator and aggregation strategies."""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from claude_experimental.parallel.aggregation import (
    AllResultsStrategy,
    BestResultStrategy,
    FirstSuccessStrategy,
    ResultAggregator,
    ScoredResult,
    calculate_quality_score,
    strategy_for_mode,
)
from claude_experimental.parallel.api import AggregationMode, IndividualResult


def _make_result(
    recipient: str = "agent",
    content: str = "output",
    exit_code: int = 0,
    duration_ms: int = 100,
) -> IndividualResult:
    return IndividualResult(
        recipient=recipient,
        content=content,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )


@pytest.mark.experimental
class TestCalculateQualityScore:
    """Quality scoring logic."""

    def test_perfect_result_high_score(self):
        r = _make_result(content="a" * 1000, exit_code=0, duration_ms=0)
        score = calculate_quality_score(r)
        assert score > 0.8

    def test_failed_result_low_score(self):
        r = _make_result(content="error traceback", exit_code=1, duration_ms=0)
        score = calculate_quality_score(r)
        assert score < 0.5

    def test_score_clamped_to_0_1(self):
        r = _make_result()
        score = calculate_quality_score(r)
        assert 0.0 <= score <= 1.0

    def test_error_keyword_penalizes(self):
        r_clean = _make_result(content="success output", exit_code=0)
        r_error = _make_result(content="error in processing", exit_code=0)
        assert calculate_quality_score(r_clean) > calculate_quality_score(r_error)


@pytest.mark.experimental
class TestBestResultStrategy:
    """BestResultStrategy picks highest-quality result."""

    def test_picks_best(self):
        strategy = BestResultStrategy()
        scored = [
            ScoredResult(_make_result(content="short"), 0.3),
            ScoredResult(_make_result(content="longer and better"), 0.9),
            ScoredResult(_make_result(content="medium"), 0.5),
        ]
        result = strategy.aggregate(scored)
        assert result == "longer and better"

    def test_empty_list_returns_none(self):
        strategy = BestResultStrategy()
        assert strategy.aggregate([]) is None

    def test_name(self):
        assert BestResultStrategy().name == "BEST_RESULT"


@pytest.mark.experimental
class TestAllResultsStrategy:
    """AllResultsStrategy returns all results ordered by quality."""

    def test_returns_all_sorted(self):
        strategy = AllResultsStrategy()
        scored = [
            ScoredResult(_make_result(content="low"), 0.2),
            ScoredResult(_make_result(content="high"), 0.9),
            ScoredResult(_make_result(content="mid"), 0.5),
        ]
        result = strategy.aggregate(scored)
        assert isinstance(result, list)
        assert result == ["high", "mid", "low"]

    def test_name(self):
        assert AllResultsStrategy().name == "ALL_RESULTS"


@pytest.mark.experimental
class TestFirstSuccessStrategy:
    """FirstSuccessStrategy returns first result with exit_code=0."""

    def test_returns_first_success(self):
        strategy = FirstSuccessStrategy()
        scored = [
            ScoredResult(_make_result(content="fail", exit_code=1), 0.1),
            ScoredResult(_make_result(content="first ok", exit_code=0), 0.5),
            ScoredResult(_make_result(content="second ok", exit_code=0), 0.8),
        ]
        assert strategy.aggregate(scored) == "first ok"

    def test_all_fail_returns_none(self):
        strategy = FirstSuccessStrategy()
        scored = [
            ScoredResult(_make_result(exit_code=1), 0.1),
        ]
        assert strategy.aggregate(scored) is None

    def test_name(self):
        assert FirstSuccessStrategy().name == "FIRST_SUCCESS"


@pytest.mark.experimental
class TestStrategyForMode:
    """strategy_for_mode factory."""

    @pytest.mark.parametrize(
        "mode,expected_type",
        [
            (AggregationMode.BEST_RESULT, BestResultStrategy),
            (AggregationMode.ALL_RESULTS, AllResultsStrategy),
            (AggregationMode.FIRST_SUCCESS, FirstSuccessStrategy),
            ("BEST_RESULT", BestResultStrategy),
            ("ALL_RESULTS", AllResultsStrategy),
        ],
    )
    def test_returns_correct_strategy(self, mode, expected_type):
        strategy = strategy_for_mode(mode)
        assert isinstance(strategy, expected_type)


@pytest.mark.experimental
class TestResultAggregator:
    """ResultAggregator integration with strategies."""

    def test_aggregate_returns_parallel_result(self):
        agg = ResultAggregator(BestResultStrategy())
        results = [
            _make_result("a1", "content a", 0, 100),
            _make_result("a2", "longer content b here", 0, 200),
        ]
        pr = agg.aggregate(results)
        assert pr.partial is False
        assert pr.execution_summary["total"] == 2
        assert pr.execution_summary["succeeded"] == 2
        assert pr.execution_summary["failed"] == 0
        assert "quality_ranking" in pr.execution_summary

    def test_aggregate_partial_when_failures(self):
        agg = ResultAggregator(BestResultStrategy())
        results = [
            _make_result("a1", "ok", 0, 100),
            _make_result("a2", "fail", 1, 50),
        ]
        pr = agg.aggregate(results)
        assert pr.partial is True
        assert pr.execution_summary["failed"] == 1

    def test_aggregate_empty_list(self):
        agg = ResultAggregator(BestResultStrategy())
        pr = agg.aggregate([])
        assert pr.results == []
        assert pr.aggregated is None
        assert pr.execution_summary["total"] == 0
