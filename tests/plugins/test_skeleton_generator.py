"""Tests for test skeleton generation."""

from pathlib import Path
import ast

from plugins.testgen.skeleton_generator import generate_test_skeleton


def _write_file(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_python_function_extraction(tmp_path: Path):
    source_file = _write_file(
        tmp_path / "module.py",
        """
def add(a, b):
    return a + b
""",
    )
    skeleton = generate_test_skeleton(source_file, {"framework": "pytest", "assertion_style": "assert"})
    assert "def test_add_happy_path():" in skeleton
    assert "def test_add_error_case():" in skeleton


def test_python_class_extraction(tmp_path: Path):
    source_file = _write_file(
        tmp_path / "module.py",
        """
class Service:
    def run(self):
        return True

    def _private(self):
        return False
""",
    )
    skeleton = generate_test_skeleton(source_file, {"framework": "pytest", "assertion_style": "assert"})
    assert "class TestService:" in skeleton
    assert "def test_run_happy_path(self):" in skeleton
    assert "def test_run_error_case(self):" in skeleton
    assert "_private" not in skeleton


def test_private_functions_excluded(tmp_path: Path):
    source_file = _write_file(
        tmp_path / "module.py",
        """
def public_fn():
    return 1

def _private_fn():
    return 2
""",
    )
    skeleton = generate_test_skeleton(source_file, {"framework": "pytest", "assertion_style": "assert"})
    assert "test_public_fn_happy_path" in skeleton
    assert "_private_fn" not in skeleton


def test_js_function_extraction(tmp_path: Path):
    source_file = _write_file(
        tmp_path / "module.js",
        """
export function add(a, b) { return a + b; }
export const run = () => true;
export default function main() { return null; }
export class Worker {}
""",
    )
    skeleton = generate_test_skeleton(source_file, {"framework": "jest", "assertion_style": "expect"})
    assert "describe('add'" in skeleton
    assert "describe('run'" in skeleton
    assert "describe('main'" in skeleton
    assert "describe('Worker'" in skeleton


def test_pytest_skeleton_syntax(tmp_path: Path):
    source_file = _write_file(
        tmp_path / "module.py",
        """
def fetch_data():
    return []
""",
    )
    skeleton = generate_test_skeleton(source_file, {"framework": "pytest", "assertion_style": "assert"})
    ast.parse(skeleton)
    assert "# TODO: implement test" in skeleton
    assert "# happy path" in skeleton
    assert "# error case" in skeleton


def test_jest_skeleton_syntax(tmp_path: Path):
    source_file = _write_file(
        tmp_path / "module.ts",
        """
export function createUser() { return {}; }
""",
    )
    skeleton = generate_test_skeleton(source_file, {"framework": "jest", "assertion_style": "expect"})
    assert "describe('createUser'" in skeleton
    assert "it('should happy path'" in skeleton
    assert "it('should error case'" in skeleton
    assert "expect(value).toBe(expected)" in skeleton


def test_empty_file_no_crash(tmp_path: Path):
    source_file = _write_file(tmp_path / "empty.py", "")
    skeleton = generate_test_skeleton(source_file, {"framework": "pytest", "assertion_style": "assert"})
    assert skeleton == ""


def test_unknown_framework_fallback(tmp_path: Path):
    source_file = _write_file(
        tmp_path / "module.py",
        """
def ping():
    return "pong"
""",
    )
    skeleton = generate_test_skeleton(source_file, {"framework": "unknown", "assertion_style": "assert"})
    assert "ping" in skeleton
    assert "TODO" in skeleton
