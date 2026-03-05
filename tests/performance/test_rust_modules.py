"""Tests for omg_natives 12 core Rust module Python fallbacks.

Verifies each of the 12 module fallback implementations and their
registration with the global REGISTRY via bind_function().
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from omg_natives._bindings import REGISTRY, get_binding
from omg_natives.grep import grep
from omg_natives.glob import glob
from omg_natives.shell import shell
from omg_natives.text import text
from omg_natives.keys import keys
from omg_natives.highlight import highlight
from omg_natives.task import task_run
from omg_natives.ps import ps
from omg_natives.prof import prof
from omg_natives.image import image
from omg_natives.clipboard import clipboard
from omg_natives.html import html


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------

class TestGrep:
    def test_grep_finds_pattern(self, tmp_path):
        """grep finds a pattern in a temp file."""
        f = tmp_path / "test.txt"
        f.write_text("hello world\nfoo bar\nhello again\n")
        results = grep("hello", str(f))
        assert len(results) == 2
        assert results[0]["file"] == str(f)
        assert results[0]["line"] == 1
        assert results[0]["text"] == "hello world"
        assert results[1]["line"] == 3

    def test_grep_no_match(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("no match here\n")
        results = grep("xyz", str(f))
        assert results == []

    def test_grep_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.txt").write_text("findme\n")
        (sub / "b.txt").write_text("findme too\n")
        results = grep("findme", str(tmp_path), recursive=True)
        assert len(results) == 2

    def test_grep_invalid_pattern(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data\n")
        results = grep("[invalid", str(f))
        assert results == []

    def test_grep_registered(self):
        spec = get_binding("grep")
        assert spec is not None
        assert spec.python_fallback is grep


# ---------------------------------------------------------------------------
# glob
# ---------------------------------------------------------------------------

class TestGlob:
    def test_glob_finds_files(self, tmp_path):
        """glob finds files matching pattern."""
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        results = glob("*.py", str(tmp_path))
        assert len(results) == 2
        assert all(r.endswith(".py") for r in results)

    def test_glob_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("")
        results = glob("**/*.py", str(tmp_path))
        assert len(results) >= 1

    def test_glob_no_match(self, tmp_path):
        (tmp_path / "file.txt").write_text("")
        results = glob("*.rs", str(tmp_path))
        assert results == []

    def test_glob_registered(self):
        spec = get_binding("glob")
        assert spec is not None
        assert spec.python_fallback is glob


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------

class TestShell:
    def test_shell_runs_command(self):
        """shell runs `echo hello`, checks stdout."""
        result = shell(["echo", "hello"])
        assert result["success"] is True
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_shell_captures_stderr(self):
        result = shell([sys.executable, "-c", "import sys; sys.stderr.write('err\\n')"])
        assert "err" in result["stderr"]

    def test_shell_failure_returncode(self):
        result = shell([sys.executable, "-c", "raise SystemExit(1)"])
        assert result["success"] is False
        assert result["returncode"] == 1

    def test_shell_rejects_shell_metacharacters(self):
        result = shell("echo hello && whoami")
        assert result["success"] is False
        assert result["returncode"] == -1
        assert "shell metacharacters" in result["stderr"].lower()

    def test_shell_registered(self):
        spec = get_binding("shell")
        assert spec is not None
        assert spec.python_fallback is shell


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------

class TestText:
    def test_text_normalize(self):
        """text normalize strips ANSI and whitespace."""
        content = "\x1b[31mhello\x1b[0m   world  \n  foo"
        result = text(content, "normalize")
        assert result == "hello world foo"

    def test_text_strip_ansi(self):
        """text strip_ansi removes escape codes."""
        content = "\x1b[31mred\x1b[0m text"
        result = text(content, "strip_ansi")
        assert result == "red text"
        assert "\x1b" not in result

    def test_text_word_count(self):
        result = text("hello world foo bar", "word_count")
        assert result == "4"

    def test_text_line_count(self):
        result = text("line1\nline2\nline3", "line_count")
        assert result == "3"

    def test_text_registered(self):
        spec = get_binding("text")
        assert spec is not None
        assert spec.python_fallback is text


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------

class TestKeys:
    def test_keys_list(self):
        """keys() returns a list of strings."""
        result = keys("list")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(k, str) for k in result)
        assert "Enter" in result
        assert "Escape" in result

    def test_keys_encode_stub(self):
        result = keys("encode")
        assert result == []

    def test_keys_registered(self):
        spec = get_binding("keys")
        assert spec is not None
        assert spec.python_fallback is keys


# ---------------------------------------------------------------------------
# highlight
# ---------------------------------------------------------------------------

class TestHighlight:
    def test_highlight_returns_code(self):
        """highlight returns code unchanged when no language."""
        code = "def foo(): pass"
        assert highlight(code) == code

    def test_highlight_with_language(self):
        code = "x = 1"
        result = highlight(code, "python")
        assert "python" in result.lower()
        assert "x = 1" in result

    def test_highlight_unknown_language(self):
        code = "some code"
        result = highlight(code, "brainfuck")
        assert result == code

    def test_highlight_registered(self):
        spec = get_binding("highlight")
        assert spec is not None
        assert spec.python_fallback is highlight


# ---------------------------------------------------------------------------
# task_run
# ---------------------------------------------------------------------------

class TestTaskRun:
    def test_task_run_success(self):
        """task_run runs a function, returns result."""
        result = task_run(lambda x, y: x + y, 3, 7)
        assert result["result"] == 10
        assert result["error"] is None

    def test_task_run_error(self):
        """task_run captures exceptions."""
        def bad():
            raise ValueError("boom")

        result = task_run(bad)
        assert result["result"] is None
        assert "boom" in result["error"]

    def test_task_run_registered(self):
        spec = get_binding("task_run")
        assert spec is not None
        assert spec.python_fallback is task_run


# ---------------------------------------------------------------------------
# ps
# ---------------------------------------------------------------------------

class TestPs:
    def test_ps_returns_list(self):
        """ps() returns a list of dicts."""
        result = ps()
        assert isinstance(result, list)
        assert len(result) >= 1
        entry = result[0]
        assert "pid" in entry
        assert "name" in entry
        assert "status" in entry
        assert isinstance(entry["pid"], int)

    def test_ps_registered(self):
        spec = get_binding("ps")
        assert spec is not None
        assert spec.python_fallback is ps


# ---------------------------------------------------------------------------
# prof
# ---------------------------------------------------------------------------

class TestProf:
    def test_prof_measures_time(self):
        """prof returns elapsed_ms > 0."""
        def slow():
            time.sleep(0.01)
            return 42

        result = prof(slow)
        assert result["result"] == 42
        assert result["elapsed_ms"] > 0
        assert result["error"] is None

    def test_prof_captures_error(self):
        def bad():
            raise RuntimeError("fail")

        result = prof(bad)
        assert result["result"] is None
        assert "fail" in result["error"]
        assert result["elapsed_ms"] >= 0

    def test_prof_registered(self):
        spec = get_binding("prof")
        assert spec is not None
        assert spec.python_fallback is prof


# ---------------------------------------------------------------------------
# image
# ---------------------------------------------------------------------------

class TestImage:
    def test_image_info_existing(self, tmp_path):
        """image info on a real file returns size_bytes > 0."""
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = image(str(f), "info")
        assert result["exists"] is True
        assert result["size_bytes"] > 0
        assert result["extension"] == ".png"
        assert result["path"] == str(f)

    def test_image_info_nonexistent(self):
        result = image("/nonexistent/file.jpg", "info")
        assert result["exists"] is False
        assert result["size_bytes"] == 0

    def test_image_registered(self):
        spec = get_binding("image")
        assert spec is not None
        assert spec.python_fallback is image


# ---------------------------------------------------------------------------
# clipboard
# ---------------------------------------------------------------------------

class TestClipboard:
    def test_clipboard_get_stub(self):
        """clipboard get returns string."""
        result = clipboard("get")
        assert isinstance(result, str)
        assert result == ""

    def test_clipboard_set_stub(self):
        result = clipboard("set", text="hello")
        assert result == "ok"

    def test_clipboard_registered(self):
        spec = get_binding("clipboard")
        assert spec is not None
        assert spec.python_fallback is clipboard


# ---------------------------------------------------------------------------
# html
# ---------------------------------------------------------------------------

class TestHtml:
    def test_html_to_text(self):
        """html to_text strips tags."""
        result = html("<p>Hello <b>world</b></p>", "to_text")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_html_to_markdown(self):
        """html to_markdown converts h1 to #."""
        result = html("<h1>Title</h1><p>Body</p>", "to_markdown")
        assert "# Title" in result
        assert "Body" in result

    def test_html_to_markdown_links(self):
        result = html('<a href="https://example.com">Click</a>', "to_markdown")
        assert "[Click](https://example.com)" in result

    def test_html_to_markdown_emphasis(self):
        result = html("<strong>bold</strong> and <em>italic</em>", "to_markdown")
        assert "**bold**" in result
        assert "*italic*" in result

    def test_html_registered(self):
        spec = get_binding("html")
        assert spec is not None
        assert spec.python_fallback is html


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    """Verify all 12 modules are registered in the global REGISTRY."""

    @pytest.mark.parametrize("name", [
        "grep", "glob", "shell", "text", "keys", "highlight",
        "task_run", "ps", "prof", "image", "clipboard", "html",
    ])
    def test_module_registered_in_registry(self, name):
        spec = get_binding(name)
        assert spec is not None, f"Binding '{name}' not found in REGISTRY"
        assert callable(spec.python_fallback)

    def test_all_12_registered(self):
        names = REGISTRY.list_names()
        expected = {"grep", "glob", "shell", "text", "keys", "highlight",
                    "task_run", "ps", "prof", "image", "clipboard", "html"}
        assert expected.issubset(set(names)), f"Missing: {expected - set(names)}"
