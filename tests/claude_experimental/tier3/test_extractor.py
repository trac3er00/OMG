"""Tests for claude_experimental.patterns.extractor — ASTExtractor."""
from __future__ import annotations

import time

import pytest

from claude_experimental.patterns.extractor import ASTExtractor, Pattern


@pytest.mark.experimental
class TestASTExtractor:
    """ASTExtractor: Python AST-based pattern extraction with caching."""

    @pytest.fixture(autouse=True)
    def _enable_flag(self, feature_flag_enabled):
        feature_flag_enabled("PATTERN_INTELLIGENCE")

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear class-level cache before each test to avoid cross-test leaks."""
        ASTExtractor._cache.clear()
        yield
        ASTExtractor._cache.clear()

    def test_extract_from_python_file(self, tmp_path):
        """Extract patterns from a real Python file and verify collection returned."""
        src = tmp_path / "sample.py"
        src.write_text(
            "import os\n"
            "import sys\n"
            "\n"
            "class MyClass:\n"
            "    def method(self):\n"
            "        pass\n"
            "\n"
            "def helper():\n"
            "    for item in range(10):\n"
            "        if item > 5:\n"
            "            print(item)\n"
        )
        extractor = ASTExtractor()
        collection = extractor.extract(str(src))

        assert isinstance(collection, list)
        assert len(collection) > 0
        assert all(isinstance(p, Pattern) for p in collection)

    def test_extract_finds_functions(self, tmp_path):
        """Functions are detected with correct type and name."""
        src = tmp_path / "funcs.py"
        src.write_text(
            "def alpha():\n    pass\n\n"
            "def beta(x):\n    return x\n\n"
            "async def gamma():\n    pass\n"
        )
        extractor = ASTExtractor()
        collection = extractor.extract(str(src))

        func_names = [p.name for p in collection if p.type == "function"]
        assert "alpha" in func_names
        assert "beta" in func_names
        assert "gamma" in func_names

    def test_extract_finds_classes(self, tmp_path):
        """Classes and class hierarchies are detected."""
        src = tmp_path / "classes.py"
        src.write_text(
            "class Base:\n    pass\n\n"
            "class Child(Base):\n    pass\n"
        )
        extractor = ASTExtractor()
        collection = extractor.extract(str(src))

        class_names = [p.name for p in collection if p.type == "class"]
        assert "Base" in class_names
        assert "Child" in class_names

        hierarchy_names = [p.name for p in collection if p.type == "class_hierarchy"]
        assert any("Child" in name and "Base" in name for name in hierarchy_names)

    def test_cache_hit_on_same_content(self, tmp_path):
        """Second extraction of unchanged file uses cache (faster)."""
        src = tmp_path / "cached.py"
        src.write_text("def foo():\n    return 42\n")
        extractor = ASTExtractor()

        t0 = time.perf_counter()
        result1 = extractor.extract(str(src))
        t1 = time.perf_counter()
        result2 = extractor.extract(str(src))
        t2 = time.perf_counter()

        # Both return same data
        assert len(result1) == len(result2)
        for p1, p2 in zip(result1, result2):
            assert p1.type == p2.type
            assert p1.name == p2.name

        # Cache should have an entry now
        assert len(ASTExtractor._cache) >= 1

    def test_extract_empty_file(self, tmp_path):
        """Empty Python file returns empty collection."""
        src = tmp_path / "empty.py"
        src.write_text("")
        extractor = ASTExtractor()
        collection = extractor.extract(str(src))
        assert collection == []

    def test_extract_syntax_error_falls_back_to_regex(self, tmp_path):
        """File with syntax errors uses regex fallback."""
        src = tmp_path / "broken.py"
        src.write_text(
            "def valid_func():\n    pass\n\n"
            "class ValidClass:\n    pass\n\n"
            "def another(:\n"  # syntax error
        )
        extractor = ASTExtractor()
        collection = extractor.extract(str(src))

        # Regex fallback should still find def and class patterns
        names = [p.name for p in collection]
        assert "valid_func" in names
        assert "ValidClass" in names

    def test_extract_non_python_file_uses_regex(self, tmp_path):
        """Non-.py files use regex fallback extraction."""
        src = tmp_path / "script.js"
        src.write_text(
            "function greet(name) {\n"
            "    return 'Hello ' + name;\n"
            "}\n"
            "class Widget {\n"
            "    constructor() {}\n"
            "}\n"
        )
        extractor = ASTExtractor()
        collection = extractor.extract(str(src))

        names = [p.name for p in collection]
        assert "greet" in names

    def test_pattern_has_all_fields(self, tmp_path):
        """Each Pattern has type, name, frequency, location, snippet."""
        src = tmp_path / "fields.py"
        src.write_text("def example():\n    return 1\n")
        extractor = ASTExtractor()
        collection = extractor.extract(str(src))

        funcs = [p for p in collection if p.type == "function" and p.name == "example"]
        assert len(funcs) >= 1
        p = funcs[0]
        assert p.type == "function"
        assert p.name == "example"
        assert p.frequency >= 1
        assert "fields.py" in p.location
        assert "def example" in p.snippet
