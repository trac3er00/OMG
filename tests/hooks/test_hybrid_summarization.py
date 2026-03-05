"""Tests for JetBrains hybrid summarization in pre-compact.py.

Validates the empirical strategy from JetBrains Research (Dec 2025):
- Keep latest N turns in full (no summarization)
- Summarize turns N+1 through M in batches
- Discard turns beyond M (rely on memory/handoff system)
- Preserve entity names, file paths, and causal relationships in summaries
"""
import importlib.util
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_CONFIG = {"full_turns": 10, "summarize_turns": 50, "batch_size": 21}


@pytest.fixture(scope="module")
def pre_compact():
    """Import pre-compact.py via importlib (hyphenated filename).

    When loaded via spec_from_file_location, __name__ != '__main__'
    so the if-guarded side-effect code does not execute.
    """
    spec = importlib.util.spec_from_file_location(
        "pre_compact", os.path.join(ROOT, "hooks", "pre-compact.py")
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_turns(count):
    """Create N test turns (index 0 = newest)."""
    turns = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        turns.append({
            "role": role,
            "content": f"Turn {i}: working on src/component_{i}.py and updating tests/test_{i}.py",
        })
    return turns


# ---------------------------------------------------------------------------
# 1. test_recent_turns_kept_full — latest 10 turns not summarized
# ---------------------------------------------------------------------------
class TestRecentTurnsKeptFull:
    def test_recent_turns_kept_full(self, pre_compact):
        """Latest 10 turns should be preserved verbatim without summarization."""
        turns = _make_turns(30)
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        assert len(result["full_turns"]) == 10
        # Verify they are the actual original turn dicts, not summaries
        for i, turn in enumerate(result["full_turns"]):
            assert turn is turns[i], f"Turn {i} should be the original object"
            assert "role" in turn
            assert "content" in turn

    def test_fewer_than_threshold_all_kept_full(self, pre_compact):
        """If total turns <= full_turns, all are kept full, nothing summarized."""
        turns = _make_turns(5)
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        assert len(result["full_turns"]) == 5
        assert result["summaries"] == []
        assert result["discarded_count"] == 0


# ---------------------------------------------------------------------------
# 2. test_middle_turns_summarized — turns 11-50 summarized in batches
# ---------------------------------------------------------------------------
class TestMiddleTurnsSummarized:
    def test_middle_turns_summarized(self, pre_compact):
        """Turns 10-49 should be summarized in batches of 21."""
        turns = _make_turns(45)
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        assert len(result["full_turns"]) == 10
        # 35 middle turns → ceil(35/21) = 2 batches
        assert len(result["summaries"]) == 2
        # Each summary is a string with batch info
        for summary in result["summaries"]:
            assert isinstance(summary, str)
            assert "Batch" in summary

    def test_batch_sizing_correct(self, pre_compact):
        """Batches should respect the configured batch_size."""
        turns = _make_turns(50)
        config = {**DEFAULT_CONFIG, "batch_size": 10}
        result = pre_compact._apply_hybrid_summarization(turns, config)

        # 40 middle turns / 10 = 4 batches
        assert len(result["summaries"]) == 4


# ---------------------------------------------------------------------------
# 3. test_old_turns_discarded — turns >50 not included
# ---------------------------------------------------------------------------
class TestOldTurnsDiscarded:
    def test_old_turns_discarded(self, pre_compact):
        """Turns beyond summarize_turns threshold should be discarded."""
        turns = _make_turns(80)
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        assert result["discarded_count"] == 30  # 80 - 50
        assert len(result["full_turns"]) == 10
        # Only turns[10:50] were summarized, not turns[50:]
        all_summary_text = " ".join(result["summaries"])
        # Turns 50-79 content should NOT appear in summaries
        assert "component_79" not in all_summary_text

    def test_exactly_at_threshold_no_discard(self, pre_compact):
        """With exactly summarize_turns count, none should be discarded."""
        turns = _make_turns(50)
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        assert result["discarded_count"] == 0


# ---------------------------------------------------------------------------
# 4. test_thresholds_configurable — settings.json values respected
# ---------------------------------------------------------------------------
class TestThresholdsConfigurable:
    def test_custom_thresholds(self, pre_compact):
        """Custom config should override default thresholds."""
        turns = _make_turns(30)
        custom_config = {"full_turns": 5, "summarize_turns": 20, "batch_size": 10}
        result = pre_compact._apply_hybrid_summarization(turns, custom_config)

        assert len(result["full_turns"]) == 5
        assert result["discarded_count"] == 10  # 30 - 20
        # 15 middle turns / 10 = 2 batches
        assert len(result["summaries"]) == 2

    def test_zero_full_turns(self, pre_compact):
        """With full_turns=0, no turns are kept verbatim."""
        turns = _make_turns(10)
        config = {"full_turns": 0, "summarize_turns": 10, "batch_size": 5}
        result = pre_compact._apply_hybrid_summarization(turns, config)

        assert len(result["full_turns"]) == 0
        assert len(result["summaries"]) == 2  # 10 / 5 = 2 batches
        assert result["discarded_count"] == 0


# ---------------------------------------------------------------------------
# 5. test_entity_preservation — entity names/file paths preserved in summaries
# ---------------------------------------------------------------------------
class TestEntityPreservation:
    def test_file_paths_preserved(self, pre_compact):
        """File paths mentioned in turns should appear in batch summaries."""
        turns = []
        for i in range(30):
            role = "user" if i % 2 == 0 else "assistant"
            turns.append({
                "role": role,
                "content": (
                    f"Turn {i}: modified hooks/pre-compact.py and "
                    f"refactored src/utils.py to improve performance"
                ),
            })
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        all_summaries = " ".join(result["summaries"])
        # File paths from the summarized range should be preserved
        assert "pre-compact.py" in all_summaries or "hooks/" in all_summaries
        assert "utils.py" in all_summaries or "src/" in all_summaries

    def test_causal_relationships_preserved(self, pre_compact):
        """Key decisions/causal language should be preserved in summaries."""
        turns = []
        for i in range(25):
            role = "user" if i % 2 == 0 else "assistant"
            turns.append({
                "role": role,
                "content": f"Turn {i}: decided to use batch processing because it reduces memory usage",
            })
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        all_summaries = " ".join(result["summaries"])
        # Causal decisions should be extracted
        assert "decided" in all_summaries.lower() or "batch processing" in all_summaries.lower()

    def test_summary_format(self, pre_compact):
        """Each summary should follow the format: Batch N (turns X-Y): ..."""
        turns = _make_turns(35)
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        for summary in result["summaries"]:
            assert re.match(r"Batch \d+", summary), f"Bad format: {summary[:80]}"


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_turns(self, pre_compact):
        """Empty turns list should return empty result."""
        result = pre_compact._apply_hybrid_summarization([], DEFAULT_CONFIG)

        assert result["full_turns"] == []
        assert result["summaries"] == []
        assert result["discarded_count"] == 0

    def test_turns_with_empty_content(self, pre_compact):
        """Turns with empty content should not crash."""
        turns = [{"role": "user", "content": ""} for _ in range(15)]
        result = pre_compact._apply_hybrid_summarization(turns, DEFAULT_CONFIG)

        assert len(result["full_turns"]) == 10
        assert len(result["summaries"]) >= 1
