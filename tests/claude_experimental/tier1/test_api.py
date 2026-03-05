"""Tests for send_parallel API and supporting data classes."""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from claude_experimental.parallel.api import (
    AggregationMode,
    DistributionMode,
    IndividualResult,
    ParallelResult,
    SendObject,
    _aggregate,
    _build_send_objects,
    _split_content,
)


@pytest.mark.experimental
class TestDistributionMode:
    """DistributionMode enum values."""

    def test_broadcast_value(self):
        assert DistributionMode.BROADCAST.value == "BROADCAST"

    def test_shard_value(self):
        assert DistributionMode.SHARD.value == "SHARD"

    def test_routed_value(self):
        assert DistributionMode.ROUTED.value == "ROUTED"


@pytest.mark.experimental
class TestAggregationMode:
    """AggregationMode enum values."""

    def test_best_result_value(self):
        assert AggregationMode.BEST_RESULT.value == "BEST_RESULT"

    def test_all_results_value(self):
        assert AggregationMode.ALL_RESULTS.value == "ALL_RESULTS"

    def test_first_success_value(self):
        assert AggregationMode.FIRST_SUCCESS.value == "FIRST_SUCCESS"


@pytest.mark.experimental
class TestSendObject:
    """SendObject dataclass."""

    def test_defaults(self):
        obj = SendObject(recipient="agent-a", content="hello")
        assert obj.priority == 0
        assert obj.dependencies == []
        assert obj.timeout == 300

    def test_custom_fields(self):
        obj = SendObject(
            recipient="agent-b",
            content="run task",
            priority=5,
            dependencies=["dep-1"],
            timeout=60,
        )
        assert obj.priority == 5
        assert obj.dependencies == ["dep-1"]
        assert obj.timeout == 60


@pytest.mark.experimental
class TestIndividualResult:
    """IndividualResult dataclass."""

    def test_fields(self):
        r = IndividualResult(
            recipient="explore",
            content="output text",
            exit_code=0,
            duration_ms=150,
        )
        assert r.recipient == "explore"
        assert r.exit_code == 0


@pytest.mark.experimental
class TestSplitContent:
    """_split_content helper."""

    def test_split_even(self):
        shards = _split_content("a b c d", 2)
        assert len(shards) == 2
        assert shards[0] == "a b"
        assert shards[1] == "c d"

    def test_split_zero_count(self):
        assert _split_content("hello", 0) == []

    def test_split_empty_content(self):
        shards = _split_content("", 3)
        assert len(shards) == 3
        assert all(s == "" for s in shards)


@pytest.mark.experimental
class TestBuildSendObjects:
    """_build_send_objects helper."""

    def test_broadcast_mode(self):
        objs = _build_send_objects(
            ["a1", "a2"], "shared prompt", DistributionMode.BROADCAST
        )
        assert len(objs) == 2
        assert objs[0].content == "shared prompt"
        assert objs[1].content == "shared prompt"

    def test_shard_mode_string_content(self):
        objs = _build_send_objects(
            ["a1", "a2"], "word1 word2 word3 word4", DistributionMode.SHARD
        )
        assert len(objs) == 2
        # Content should be sharded across recipients
        combined = objs[0].content + " " + objs[1].content
        assert "word1" in combined
        assert "word4" in combined

    def test_routed_mode_dict_content(self):
        objs = _build_send_objects(
            ["a1", "a2"],
            {"a1": "task for a1", "a2": "task for a2"},
            DistributionMode.ROUTED,
        )
        assert objs[0].content == "task for a1"
        assert objs[1].content == "task for a2"

    def test_passthrough_send_objects(self):
        original = [
            SendObject(recipient="x", content="c1"),
            SendObject(recipient="y", content="c2"),
        ]
        result = _build_send_objects(original, "", DistributionMode.BROADCAST)
        assert result == original


@pytest.mark.experimental
class TestAggregate:
    """_aggregate function."""

    def _make_results(self) -> list[IndividualResult]:
        return [
            IndividualResult("a1", "short", 0, 100),
            IndividualResult("a2", "longer content here", 0, 200),
            IndividualResult("a3", "failed", 1, 50),
        ]

    def test_all_results_mode(self):
        results = self._make_results()
        agg = _aggregate(results, AggregationMode.ALL_RESULTS)
        assert isinstance(agg, list)
        assert len(agg) == 3

    def test_first_success_mode(self):
        results = self._make_results()
        agg = _aggregate(results, AggregationMode.FIRST_SUCCESS)
        # First successful result is "short" (exit_code=0)
        assert agg == "short"

    def test_first_success_none_when_all_fail(self):
        results = [IndividualResult("a1", "err", 1, 100)]
        agg = _aggregate(results, AggregationMode.FIRST_SUCCESS)
        assert agg is None

    def test_best_result_picks_longest_successful(self):
        results = self._make_results()
        agg = _aggregate(results, AggregationMode.BEST_RESULT)
        # "longer content here" is the longest successful content
        assert agg == "longer content here"

    def test_best_result_empty_list(self):
        agg = _aggregate([], AggregationMode.BEST_RESULT)
        assert agg is None


@pytest.mark.experimental
class TestParallelResult:
    """ParallelResult dataclass."""

    def test_fields(self):
        r = ParallelResult(
            results=[],
            aggregated=None,
            execution_summary={"total": 0},
            partial=False,
        )
        assert r.partial is False
        assert r.results == []
