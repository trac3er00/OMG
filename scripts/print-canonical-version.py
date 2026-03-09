#!/usr/bin/env python3
"""Zero-dependency canonical version extractor using AST parsing.

Reads CANONICAL_VERSION from runtime/adoption.py without importing it.
Prints the semver string (e.g. "2.1.1") with trailing newline.
Exit code 0 on success, non-zero on parse failure.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast


def extract_canonical_version(source_file: Path) -> str | None:
    """Extract CANONICAL_VERSION from source file using AST parsing.
    
    Args:
        source_file: Path to runtime/adoption.py
        
    Returns:
        The version string (e.g. "2.1.1") or None if not found/invalid
    """
    try:
        source_code = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"Error reading {source_file}: {e}", file=sys.stderr)
        return None
    
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"Syntax error in {source_file}: {e}", file=sys.stderr)
        return None
    
    # Walk the AST looking for CANONICAL_VERSION assignment
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CANONICAL_VERSION":
                    if isinstance(node.value, ast.Constant):
                        val = node.value.value
                        if isinstance(val, str):
                            return cast(str, val)
                    elif isinstance(node.value, ast.Str):
                        return cast(str, node.value.s)
    
    return None


def main() -> int:
    """Main entry point."""
    # Resolve path relative to repo root (where script is called from)
    # First try: relative to script location (normal case)
    scripts_dir = Path(__file__).resolve().parent
    repo_root = scripts_dir.parent
    adoption_file = repo_root / "runtime" / "adoption.py"
    
    # Fallback: if not found, try current working directory
    if not adoption_file.exists():
        adoption_file = Path.cwd() / "runtime" / "adoption.py"
    
    if not adoption_file.exists():
        print(f"Error: {adoption_file} not found", file=sys.stderr)
        return 1
    
    version = extract_canonical_version(adoption_file)
    
    if version is None:
        print(f"Error: CANONICAL_VERSION not found in {adoption_file}", file=sys.stderr)
        return 1
    
    # Print the version with trailing newline
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
