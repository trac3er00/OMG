from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isqrt
from pathlib import Path
from statistics import mean, pstdev

from claude_experimental.patterns.extractor import ASTExtractor, Pattern


SEQUENTIAL = "sequential"
STRUCTURAL = "structural"


@dataclass(frozen=True)
class PatternReport:
    patterns: list[Pattern]
    frequencies: dict[str, int]
    deviations: dict[str, float]
    baseline: dict[str, float]
    total_files: int


class PatternMiner:
    def __init__(self, extractor: ASTExtractor | None = None) -> None:
        self._extractor: ASTExtractor = extractor or ASTExtractor()

    def mine(
        self,
        directory: str,
        min_support: float = 0.05,
        pattern_type: str = SEQUENTIAL,
    ) -> PatternReport:
        import claude_experimental.patterns as patterns

        getattr(patterns, "_require_enabled")()

        requested_type = pattern_type.lower()
        if requested_type not in {SEQUENTIAL, STRUCTURAL}:
            raise ValueError(f"Unsupported pattern_type: {pattern_type}")

        root = Path(directory)
        files = self._discover_files(root)
        if not files:
            return PatternReport(
                patterns=[],
                frequencies={},
                deviations={},
                baseline={"mean": 0.0, "std_dev": 0.0, "window_size": 0.0, "anomaly_zscore": 2.0},
                total_files=0,
            )

        per_file_patterns: list[list[Pattern]] = []
        for file_path in files:
            try:
                per_file_patterns.append(self._extractor.extract(str(file_path)))
            except Exception:
                per_file_patterns.append([])

        mined_by_file: list[list[Pattern]] = []
        for source_patterns in per_file_patterns:
            if requested_type == SEQUENTIAL:
                mined_by_file.append(self._sequential_patterns(source_patterns))
            else:
                mined_by_file.append(self._structural_patterns(source_patterns))

        frequency_counter: Counter[str] = Counter()
        file_support: Counter[str] = Counter()
        representatives: dict[str, Pattern] = {}
        file_pattern_keys: list[list[str]] = []

        for patterns in mined_by_file:
            keys_for_file: list[str] = []
            for pattern in patterns:
                key = self._pattern_key(pattern)
                frequency_counter[key] += 1
                keys_for_file.append(key)
                _ = representatives.setdefault(key, pattern)

            for key in set(keys_for_file):
                file_support[key] += 1

            file_pattern_keys.append(keys_for_file)

        total_files = len(files)
        min_files = max(1, int(total_files * min_support))
        selected_keys = {
            key
            for key, support_count in file_support.items()
            if support_count >= min_files
        }

        filtered_frequencies = {
            key: count for key, count in frequency_counter.items() if key in selected_keys
        }
        filtered_patterns = [
            Pattern(
                type=representatives[key].type,
                name=representatives[key].name,
                frequency=filtered_frequencies[key],
                location=representatives[key].location,
                snippet=representatives[key].snippet,
            )
            for key in sorted(filtered_frequencies)
        ]

        window_counters = self._sliding_window_counters(file_pattern_keys)
        deviations = self._compute_deviation_scores(
            selected_keys=selected_keys,
            window_counters=window_counters,
        )

        baseline = self._compute_baseline(filtered_frequencies, len(window_counters))

        return PatternReport(
            patterns=filtered_patterns,
            frequencies=filtered_frequencies,
            deviations=deviations,
            baseline=baseline,
            total_files=total_files,
        )

    @staticmethod
    def _discover_files(directory: Path) -> list[Path]:
        if directory.is_file():
            return [directory]

        files = [path for path in directory.rglob("*") if path.is_file()]
        files.sort()
        return files

    @staticmethod
    def _pattern_key(pattern: Pattern) -> str:
        return f"{pattern.type}:{pattern.name}"

    @staticmethod
    def _sequential_patterns(patterns: list[Pattern]) -> list[Pattern]:
        imports = [pattern for pattern in patterns if pattern.type == "import"]
        if len(imports) < 2:
            return []

        chains: list[Pattern] = []
        for current_pattern, next_pattern in zip(imports, imports[1:]):
            chain_name = f"{current_pattern.name}->{next_pattern.name}"
            chains.append(
                Pattern(
                    type=SEQUENTIAL,
                    name=chain_name,
                    frequency=1,
                    location=next_pattern.location,
                    snippet=f"{current_pattern.name} -> {next_pattern.name}",
                )
            )
        return chains

    @staticmethod
    def _structural_patterns(patterns: list[Pattern]) -> list[Pattern]:
        return [pattern for pattern in patterns if pattern.type == "class_hierarchy"]

    @staticmethod
    def _sliding_window_counters(file_pattern_keys: list[list[str]]) -> list[Counter[str]]:
        total_files = len(file_pattern_keys)
        if total_files == 0:
            return []

        window_size = max(1, isqrt(total_files))
        window_counters: list[Counter[str]] = []
        for start in range(0, total_files):
            end = min(total_files, start + window_size)
            counter: Counter[str] = Counter()
            for keys in file_pattern_keys[start:end]:
                counter.update(keys)
            window_counters.append(counter)

        return window_counters

    @staticmethod
    def _compute_deviation_scores(
        selected_keys: set[str],
        window_counters: list[Counter[str]],
    ) -> dict[str, float]:
        if not selected_keys or not window_counters:
            return {}

        scores: dict[str, float] = {}
        for key in sorted(selected_keys):
            counts = [counter.get(key, 0) for counter in window_counters]
            mu = mean(counts)
            sigma = pstdev(counts)
            peak_frequency = max(counts)
            z_score = 0.0 if sigma == 0.0 else (peak_frequency - mu) / sigma
            scores[key] = z_score
        return scores

    @staticmethod
    def _compute_baseline(frequencies: dict[str, int], window_count: int) -> dict[str, float]:
        values = list(frequencies.values())
        if values:
            mu = mean(values)
            sigma = pstdev(values)
        else:
            mu = 0.0
            sigma = 0.0

        return {
            "mean": float(mu),
            "std_dev": float(sigma),
            "window_size": float(window_count),
            "anomaly_zscore": 2.0,
        }

    @staticmethod
    def anomalous_patterns(report: PatternReport, threshold: float = 2.0) -> dict[str, float]:
        return {
            key: score
            for key, score in report.deviations.items()
            if abs(score) > threshold
        }
