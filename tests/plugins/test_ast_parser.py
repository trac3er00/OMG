"""Tests for Python AST dependency parsing and graph building."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Callable, cast

_ast_parser = importlib.import_module("plugins.viz.ast_parser")
parse_python_imports = cast(Callable[[str], list[str]], _ast_parser.parse_python_imports)
build_dependency_graph = cast(Callable[[str], dict[str, object]], _ast_parser.build_dependency_graph)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def test_parse_simple_import(tmp_path: Path) -> None:
    file_path = tmp_path / "m.py"
    _write(file_path, "import os\n")
    assert parse_python_imports(str(file_path)) == ["os"]


def test_parse_from_import(tmp_path: Path) -> None:
    file_path = tmp_path / "m.py"
    _write(file_path, "from pathlib import Path\n")
    assert parse_python_imports(str(file_path)) == ["pathlib"]


def test_parse_relative_import(tmp_path: Path) -> None:
    file_path = tmp_path / "m.py"
    _write(file_path, "from . import utils\n")
    assert parse_python_imports(str(file_path)) == ["."]


def test_parse_multiple_imports(tmp_path: Path) -> None:
    file_path = tmp_path / "m.py"
    _write(
        file_path,
        "import os\nimport sys\nfrom pathlib import Path\nfrom .pkg import thing\n",
    )
    assert parse_python_imports(str(file_path)) == ["os", "sys", "pathlib", ".pkg"]


def test_build_graph_adjacency_list(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "a.py", "import pkg.b\n")
    _write(tmp_path / "pkg" / "b.py", "from pkg import c\n")
    _write(tmp_path / "pkg" / "c.py", "")

    result = build_dependency_graph(str(tmp_path))
    graph = cast(dict[str, list[str]], result["graph"])

    assert graph["pkg.a"] == ["pkg.b"]
    assert graph["pkg.b"] == ["pkg"]
    assert graph["pkg.c"] == []


def test_circular_dependency_detected(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "import a\n")

    result = build_dependency_graph(str(tmp_path))
    stats = cast(dict[str, object], result["stats"])
    cycles = cast(list[list[str]], result["cycles"])

    assert stats["has_cycles"] is True
    assert any(cycle[0] == "a" and cycle[-1] == "a" for cycle in cycles)


def test_graph_stats_computed(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "import c\n")
    _write(tmp_path / "c.py", "")

    result = build_dependency_graph(str(tmp_path))
    stats = cast(dict[str, object], result["stats"])

    assert set(stats.keys()) == {"module_count", "edge_count", "max_depth", "has_cycles"}
    assert stats["module_count"] == 3
    assert stats["edge_count"] == 2
    assert stats["has_cycles"] is False


def test_empty_file_no_crash(tmp_path: Path) -> None:
    file_path = tmp_path / "empty.py"
    _write(file_path, "")
    assert parse_python_imports(str(file_path)) == []


def test_graph_written_to_json_adjacency_list(tmp_path: Path) -> None:
    _write(tmp_path / "m.py", "import os\n")

    result = build_dependency_graph(str(tmp_path))

    graph_path = tmp_path / ".omg" / "state" / "dependency-graph.json"
    assert graph_path.exists()

    payload = cast(dict[str, object], json.loads(graph_path.read_text(encoding="utf-8")))
    assert payload["graph"] == result["graph"]
    assert payload["stats"] == result["stats"]
    assert isinstance(payload["cycles"], list)
