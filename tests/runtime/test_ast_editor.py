# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from __future__ import annotations

from pathlib import Path

from runtime.ast_editor import ASTEditor


def test_multi_replace_simple_pattern(tmp_path: Path) -> None:
    file_path = tmp_path / "test.py"
    _ = file_path.write_text("print('hello')\nprint('world')\n", encoding="utf-8")

    editor = ASTEditor()
    results = editor.multi_replace(str(file_path), [("print", "logger.info")], language="python")

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].replacements_made > 0
    assert "logger.info('hello')" in file_path.read_text(encoding="utf-8")


def test_multi_replace_multiple_patterns(tmp_path: Path) -> None:
    file_path = tmp_path / "test.js"
    _ = file_path.write_text("console.log('a')\nconsole.error('b')\n", encoding="utf-8")

    editor = ASTEditor()
    results = editor.multi_replace(
        str(file_path),
        [("console.log", "logger.info"), ("console.error", "logger.error")],
        language="javascript",
    )

    assert len(results) == 2
    assert all(result.success for result in results)
    content = file_path.read_text(encoding="utf-8")
    assert "console.log" not in content
    assert "console.error" not in content
    assert "logger.info('a')" in content
    assert "logger.error('b')" in content


def test_undo_reverts_changes(tmp_path: Path) -> None:
    file_path = tmp_path / "test.py"
    original = "print('hello')\n"
    _ = file_path.write_text(original, encoding="utf-8")

    editor = ASTEditor()
    editor.multi_replace(str(file_path), [("print", "logger.info")], language="python")

    assert "logger.info" in file_path.read_text(encoding="utf-8")
    assert editor.undo_last() is True
    assert file_path.read_text(encoding="utf-8") == original


def test_nonexistent_file_returns_error() -> None:
    editor = ASTEditor()

    results = editor.multi_replace("/nonexistent/file.py", [("x", "y")])

    assert len(results) == 1
    assert results[0].success is False
    assert "not found" in results[0].error.lower()


def test_history_records_operations(tmp_path: Path) -> None:
    file_path = tmp_path / "test.py"
    _ = file_path.write_text("x = 1\n", encoding="utf-8")

    editor = ASTEditor()
    editor.multi_replace(str(file_path), [("x = 1", "x = 2")])

    history = editor.get_history()
    assert len(history) == 1
    assert history[0]["file"] == str(file_path)
    assert history[0]["pattern"] == "x = 1"
    assert history[0]["applied"] is True


def test_undo_no_history_returns_false() -> None:
    editor = ASTEditor()
    assert editor.undo_last() is False


def test_extract_function_replaces_snippet_and_appends_function(tmp_path: Path) -> None:
    file_path = tmp_path / "extract_me.py"
    _ = file_path.write_text(
        (
            "def main():\n"
            "    value = 1\n"
            "    print(value)\n"
            "    return value\n"
        ),
        encoding="utf-8",
    )

    snippet = "    value = 1\n    print(value)"
    editor = ASTEditor()
    result = editor.extract_function(
        file_path,
        snippet,
        "emit_value",
        parameters=[],
        language="python",
    )

    assert result.success is True
    content = file_path.read_text(encoding="utf-8")
    assert "    emit_value()" in content
    assert "def emit_value():\n    value = 1\n    print(value)\n" in content


def test_extract_function_undo_restores_original_file(tmp_path: Path) -> None:
    file_path = tmp_path / "extract_undo.py"
    original = "def main():\n    print('hi')\n    return 1\n"
    _ = file_path.write_text(original, encoding="utf-8")

    editor = ASTEditor()
    result = editor.extract_function(file_path, "    print('hi')", "say_hi")

    assert result.success is True
    assert editor.undo_last() is True
    assert file_path.read_text(encoding="utf-8") == original
