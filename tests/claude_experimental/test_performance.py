from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, cast

import pytest

from claude_experimental.memory.api import recall
from claude_experimental.memory.store import MemoryStore
from claude_experimental.patterns.extractor import ASTExtractor
from hooks import _common


if "." not in sys.path:
    sys.path.insert(0, ".")


GET_FEATURE_FLAG = cast(Callable[[str, bool], bool], getattr(_common, "get_feature_flag"))


@pytest.mark.experimental
class TestPerformanceBenchmarks:
    @pytest.fixture(autouse=True)
    def _enable_features(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("OMG_EXPERIMENTAL_MEMORY_ENABLED", "1")
        monkeypatch.setenv("OMG_PATTERN_INTELLIGENCE_ENABLED", "1")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    @pytest.fixture(autouse=True)
    def _clear_extractor_cache(self):
        cache = getattr(ASTExtractor, "_cache", None)
        if isinstance(cache, dict):
            cache.clear()
        yield
        if isinstance(cache, dict):
            cache.clear()

    def test_memory_recall_latency_under_100ms_with_1000_entries(self):
        store = MemoryStore(scope="project")
        for idx in range(1000):
            _ = store.save(
                content=f"benchmark memory entry {idx} for recall latency test",
                memory_type="semantic",
                importance=0.8,
                scope="project",
            )

        start = time.perf_counter()
        results = recall(
            query="benchmark memory",
            limit=10,
            scope_filter="project",
            min_relevance=0.0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        print(f"Memory recall latency (1000 entries): {elapsed_ms:.3f} ms")
        assert len(results) >= 1
        assert elapsed_ms < 100.0

    def test_pattern_analysis_under_5s_for_10_python_files(self, tmp_path: Path):
        files: list[str] = []
        for idx in range(10):
            source = tmp_path / f"sample_{idx}.py"
            _ = source.write_text(
                """import os
import sys

class BenchClass:
    def compute(self, value):
        if value > 0:
            for item in range(value):
                try:
                    _ = item + 1
                except Exception:
                    pass
        return value

def helper(x):
    return x * 2
""",
                encoding="utf-8",
            )
            files.append(str(source))

        extractor = ASTExtractor()

        start = time.perf_counter()
        total_patterns = 0
        for path in files:
            total_patterns += len(extractor.extract(path))
        elapsed_s = time.perf_counter() - start

        print(f"Pattern analysis latency (10 files): {elapsed_s:.3f} s")
        assert total_patterns > 0
        assert elapsed_s < 5.0

    def test_feature_flag_hook_overhead_under_5ms(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OMG_EXPERIMENTAL_MEMORY_ENABLED", "1")

        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            _ = GET_FEATURE_FLAG("EXPERIMENTAL_MEMORY", False)
        elapsed_ms = ((time.perf_counter() - start) * 1000.0) / iterations

        print(f"Feature flag hook overhead (avg): {elapsed_ms:.6f} ms")
        assert elapsed_ms < 5.0
