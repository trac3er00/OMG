"""Tests for the canonical version extractor script."""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def extract_canonical_version(source_file: Path) -> str | None:
    """Extract CANONICAL_VERSION from source file using AST parsing."""
    try:
        source_code = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CANONICAL_VERSION":
                    if isinstance(node.value, ast.Constant):
                        if isinstance(node.value.value, str):
                            return node.value.value
                    elif isinstance(node.value, ast.Str):
                        return node.value.s
    
    return None


def test_extract_canonical_version_success():
    """Test successful extraction of CANONICAL_VERSION from adoption.py."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    script = repo_root / "scripts" / "print-canonical-version.py"
    
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert result.stdout.strip() == "2.1.1", f"Unexpected version: {result.stdout}"


def test_extract_canonical_version_output_format():
    """Test that output is plain semver with trailing newline."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    script = repo_root / "scripts" / "print-canonical-version.py"
    
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0
    assert result.stdout.endswith("\n"), "Output must end with newline"
    assert result.stdout == "2.1.1\n", f"Output format incorrect: {repr(result.stdout)}"


def test_extract_canonical_version_no_extra_output():
    """Test that there is no extra logging or output."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    script = repo_root / "scripts" / "print-canonical-version.py"
    
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0
    assert result.stderr == "", f"Unexpected stderr: {result.stderr}"
    assert result.stdout.count("\n") == 1, "Output should have exactly one newline"


def test_extract_canonical_version_ast_missing_file():
    """Test AST extraction fails gracefully when file is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        missing_file = tmpdir_path / "adoption.py"
        
        result = extract_canonical_version(missing_file)
        assert result is None, "Should return None when file is missing"


def test_extract_canonical_version_ast_malformed_source():
    """Test AST extraction fails gracefully on syntax errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        adoption_file = tmpdir_path / "adoption.py"
        adoption_file.write_text("CANONICAL_VERSION = \"2.1.1\"\nthis is not valid python !!!")
        
        result = extract_canonical_version(adoption_file)
        assert result is None, "Should return None on syntax error"


def test_extract_canonical_version_ast_missing_constant():
    """Test AST extraction returns None when CANONICAL_VERSION is not defined."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        adoption_file = tmpdir_path / "adoption.py"
        adoption_file.write_text("SOME_OTHER_CONSTANT = \"1.0.0\"\n")
        
        result = extract_canonical_version(adoption_file)
        assert result is None, "Should return None when CANONICAL_VERSION not found"


def test_extract_canonical_version_ast_success():
    """Test AST extraction succeeds with valid source."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        adoption_file = tmpdir_path / "adoption.py"
        adoption_file.write_text('CANONICAL_VERSION = "3.2.1"\nOTHER = "value"\n')
        
        result = extract_canonical_version(adoption_file)
        assert result == "3.2.1", f"Expected '3.2.1', got {result}"
