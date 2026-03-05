"""Tests for claude_experimental.patterns.mining — PatternMiner."""
from __future__ import annotations

import pytest

from claude_experimental.patterns.extractor import ASTExtractor
from claude_experimental.patterns.mining import PatternMiner, PatternReport


@pytest.mark.experimental
class TestPatternMiner:
    """PatternMiner: frequency-based pattern mining with deviation scoring."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PATTERN_INTELLIGENCE")

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        ASTExtractor._cache.clear()
        yield
        ASTExtractor._cache.clear()

    def _create_python_files(self, tmp_path, count=3):
        """Helper: create multiple Python files with shared import patterns."""
        for i in range(count):
            src = tmp_path / f"mod_{i}.py"
            src.write_text(
                "import os\n"
                "import sys\n"
                "import json\n"
                "\n"
                f"def func_{i}():\n"
                f"    return {i}\n"
                "\n"
                f"class Cls_{i}:\n"
                "    pass\n"
            )
        return tmp_path

    def test_mine_directory_returns_report(self, tmp_path):
        """Mining a directory with Python files returns a PatternReport."""
        self._create_python_files(tmp_path, count=3)
        miner = PatternMiner()
        report = miner.mine(str(tmp_path))

        assert isinstance(report, PatternReport)
        assert report.total_files >= 3
        assert isinstance(report.patterns, list)
        assert isinstance(report.frequencies, dict)
        assert isinstance(report.deviations, dict)
        assert isinstance(report.baseline, dict)

    def test_mine_finds_sequential_patterns(self, tmp_path):
        """Sequential mining detects import chain patterns across files."""
        self._create_python_files(tmp_path, count=4)
        miner = PatternMiner()
        report = miner.mine(str(tmp_path), pattern_type="sequential")

        # With os, sys, json imports in each file, chains like os->sys should appear
        assert len(report.patterns) > 0
        assert len(report.frequencies) > 0
        # At least one sequential pattern should have support across files
        chain_names = [p.name for p in report.patterns]
        assert any("->" in name for name in chain_names)

    def test_mine_empty_directory(self, tmp_path):
        """Mining an empty directory returns an empty report."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        miner = PatternMiner()
        report = miner.mine(str(empty_dir))

        assert report.total_files == 0
        assert report.patterns == []
        assert report.frequencies == {}

    def test_mine_invalid_pattern_type(self, tmp_path):
        """Invalid pattern_type raises ValueError."""
        src = tmp_path / "x.py"
        src.write_text("x = 1\n")
        miner = PatternMiner()
        with pytest.raises(ValueError, match="Unsupported pattern_type"):
            miner.mine(str(tmp_path), pattern_type="invalid_type")

    def test_mine_baseline_has_expected_keys(self, tmp_path):
        """Baseline dict contains mean, std_dev, window_size, anomaly_zscore."""
        self._create_python_files(tmp_path, count=2)
        miner = PatternMiner()
        report = miner.mine(str(tmp_path))

        assert "mean" in report.baseline
        assert "std_dev" in report.baseline
        assert "window_size" in report.baseline
        assert "anomaly_zscore" in report.baseline
        assert report.baseline["anomaly_zscore"] == 2.0
