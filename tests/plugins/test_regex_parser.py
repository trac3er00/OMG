"""Tests for plugins/viz/regex_parser.py."""
import importlib
import os
import sys
from pathlib import Path
from typing import Callable, NotRequired, TypedDict, cast


class ParseResult(TypedDict):
    imports: list[str]
    accuracy: str
    language: str
    error: NotRequired[str]


# Add project root to sys.path for import
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_regex_parser = importlib.import_module("plugins.viz.regex_parser")
parse_go_imports = cast(Callable[[str], ParseResult], _regex_parser.parse_go_imports)
parse_js_imports = cast(Callable[[str], ParseResult], _regex_parser.parse_js_imports)


def test_js_es6_import(tmp_path: Path):
    file_path = tmp_path / "sample.js"
    _ = file_path.write_text("import X from 'pkg-a'\n")

    result = parse_js_imports(str(file_path))

    assert "pkg-a" in result["imports"]


def test_js_require(tmp_path: Path):
    file_path = tmp_path / "sample.js"
    _ = file_path.write_text("const x = require('pkg-b')\n")

    result = parse_js_imports(str(file_path))

    assert "pkg-b" in result["imports"]


def test_js_export_from(tmp_path: Path):
    file_path = tmp_path / "sample.ts"
    _ = file_path.write_text("export * from 'pkg-c'\n")

    result = parse_js_imports(str(file_path))

    assert "pkg-c" in result["imports"]


def test_js_dynamic_import(tmp_path: Path):
    file_path = tmp_path / "sample.ts"
    _ = file_path.write_text("const mod = import('pkg-d')\n")

    result = parse_js_imports(str(file_path))

    assert "pkg-d" in result["imports"]


def test_go_single_import(tmp_path: Path):
    file_path = tmp_path / "main.go"
    _ = file_path.write_text('package main\nimport "fmt"\n')

    result = parse_go_imports(str(file_path))

    assert "fmt" in result["imports"]


def test_go_multi_import_block(tmp_path: Path):
    file_path = tmp_path / "main.go"
    _ = file_path.write_text('package main\nimport (\n    "fmt"\n    "net/http"\n)\n')

    result = parse_go_imports(str(file_path))

    assert "fmt" in result["imports"]
    assert "net/http" in result["imports"]


def test_missing_file_no_crash(tmp_path: Path):
    file_path = tmp_path / "missing.js"

    result = parse_js_imports(str(file_path))

    assert result["imports"] == []


def test_accuracy_metadata_in_result(tmp_path: Path):
    js_file = tmp_path / "sample.js"
    go_file = tmp_path / "main.go"
    _ = js_file.write_text("import X from 'pkg-a'\n")
    _ = go_file.write_text('package main\nimport "fmt"\n')

    js_result = parse_js_imports(str(js_file))
    go_result = parse_go_imports(str(go_file))

    assert js_result["accuracy"] == "regex-70%"
    assert js_result["language"] == "javascript"
    assert go_result["accuracy"] == "regex-80%"
    assert go_result["language"] == "go"


def test_unparseable_binary_file_returns_error_note(tmp_path: Path):
    file_path = tmp_path / "binary.js"
    _ = file_path.write_bytes(b"\xff\xfe\x00\x00")

    result = parse_js_imports(str(file_path))

    assert result["imports"] == []
    assert "error" in result
