"""Tests for claude_experimental.patterns.antipatterns — AntiPatternDetector."""
from __future__ import annotations

import pytest

from claude_experimental.patterns.antipatterns import (
    AntiPatternDetector,
    AntiPatternViolation,
)


@pytest.mark.experimental
class TestAntiPatternDetector:
    """AntiPatternDetector: code quality scoring via anti-pattern detection."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PATTERN_INTELLIGENCE")

    def test_detect_bare_except(self, tmp_path):
        """Bare 'except:' without specific type is detected."""
        src = tmp_path / "bare.py"
        src.write_text(
            "try:\n"
            "    x = 1 / 0\n"
            "except:\n"
            "    pass\n"
        )
        detector = AntiPatternDetector()
        violations = detector.detect(str(src))

        bare = [v for v in violations if v.rule_name == "bare_except"]
        assert len(bare) >= 1
        assert bare[0].severity == "high"

    def test_detect_mutable_default(self, tmp_path):
        """Mutable default arguments (list, dict) are detected."""
        src = tmp_path / "mutable.py"
        src.write_text(
            "def bad_func(items=[]):\n"
            "    items.append(1)\n"
            "    return items\n"
            "\n"
            "def also_bad(data={}):\n"
            "    return data\n"
        )
        detector = AntiPatternDetector()
        violations = detector.detect(str(src))

        mut = [v for v in violations if v.rule_name == "mutable_default"]
        assert len(mut) >= 2
        assert all(v.severity == "high" for v in mut)

    def test_detect_deep_nesting(self, tmp_path):
        """Deeply nested code (>4 levels) is detected."""
        # 5+ indentation levels: module → def → if → if → if → if → if
        src = tmp_path / "nested.py"
        src.write_text(
            "def deep():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                if True:\n"
            "                    if True:\n"
            "                        x = 1\n"
        )
        detector = AntiPatternDetector()
        violations = detector.detect(str(src))

        deep = [v for v in violations if v.rule_name == "deep_nesting"]
        assert len(deep) >= 1
        assert deep[0].severity == "medium"

    def test_clean_file_high_score(self, tmp_path):
        """A clean Python file with no anti-patterns scores > 0.9."""
        src = tmp_path / "clean.py"
        src.write_text(
            "\"\"\"A clean module.\"\"\"\n"
            "\n"
            "\n"
            "def add(a: int, b: int) -> int:\n"
            "    \"\"\"Add two numbers.\"\"\"\n"
            "    return a + b\n"
            "\n"
            "\n"
            "def multiply(a: int, b: int) -> int:\n"
            "    \"\"\"Multiply two numbers.\"\"\"\n"
            "    return a * b\n"
        )
        detector = AntiPatternDetector()
        score = detector.score(str(src))

        assert score > 0.9

    def test_dirty_file_low_score(self, tmp_path):
        """File with 5+ anti-patterns scores < 0.5."""
        src = tmp_path / "dirty.py"
        src.write_text(
            "import os\n"  # unused import (low)
            "\n"
            "def bad(items=[]):\n"  # mutable default (high)
            "    try:\n"
            "        x = 1 / 0\n"
            "    except:\n"  # bare except (high)
            "        pass\n"  # empty except (high)
            "    result = 42 * 37\n"  # magic numbers (low × 2)
            "    print(result)\n"  # print statement (low)
            "    return items\n"
            "\n"
            "def another():\n"
            "    try:\n"
            "        pass\n"
            "    except:\n"  # bare except (high)
            "        pass\n"  # empty except (high)
        )
        detector = AntiPatternDetector()
        score = detector.score(str(src))

        assert score < 0.5

    def test_add_custom_rule(self, tmp_path):
        """Custom rules can be added via add_rule()."""
        src = tmp_path / "custom.py"
        src.write_text("TODO_ITEM = 'fix this'\n")

        def detect_todo(source: str, path: str):
            violations = []
            for lineno, line in enumerate(source.splitlines(), start=1):
                if "TODO" in line:
                    violations.append(AntiPatternViolation(
                        rule_name="todo_found",
                        severity="low",
                        line=lineno,
                        description="TODO comment found",
                        snippet=line.strip(),
                    ))
            return violations

        detector = AntiPatternDetector()
        detector.add_rule(detect_todo)
        violations = detector.detect(str(src))

        todos = [v for v in violations if v.rule_name == "todo_found"]
        assert len(todos) >= 1

    def test_empty_except_detected(self, tmp_path):
        """Empty except blocks (except: pass) are detected as high severity."""
        src = tmp_path / "empty_ex.py"
        src.write_text(
            "try:\n"
            "    x = 1\n"
            "except Exception:\n"
            "    pass\n"
        )
        detector = AntiPatternDetector()
        violations = detector.detect(str(src))

        empty = [v for v in violations if v.rule_name == "empty_except"]
        assert len(empty) >= 1
        assert empty[0].severity == "high"
