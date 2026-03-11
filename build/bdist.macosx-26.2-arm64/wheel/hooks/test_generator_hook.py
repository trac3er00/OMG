#!/usr/bin/env python3
"""
PostToolUse Hook: Test Generation Suggestion
Suggests test generation when source files are modified without corresponding tests.
Feature-gated under TEST_GENERATION flag.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_common():
    path = os.path.join(HOOKS_DIR, "_common.py")
    spec = importlib.util.spec_from_file_location("_common", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load _common.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_common = _load_common()
setup_crash_handler = _common.setup_crash_handler
json_input = _common.json_input
get_feature_flag = _common.get_feature_flag
get_project_dir = _common.get_project_dir

# Tool names that modify files
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})

# Patterns indicating a file is a test file
TEST_FILE_PATTERNS = [
    r"(?:^|/)test_",       # test_ prefix (Python convention)
    r"_test\.",             # _test suffix before extension
    r"\.spec\.",            # .spec. (JS/TS convention)
    r"\.test\.",            # .test. (JS/TS convention)
    r"(?:^|/)tests/",      # inside tests/ directory
    r"(?:^|/)test/",       # inside test/ directory
    r"(?:^|/)__tests__/",  # inside __tests__/ directory
]

_TEST_RE = re.compile("|".join(TEST_FILE_PATTERNS))


def _is_test_file(file_path: str) -> bool:
    """Return True if the file path looks like a test file."""
    normalized = file_path.replace("\\", "/")
    return bool(_TEST_RE.search(normalized))


def _find_corresponding_test(file_path: str, project_dir: str) -> bool:
    """Return True if a corresponding test file exists for the given source file."""
    basename = os.path.basename(file_path)
    name, ext = os.path.splitext(basename)
    dir_part = os.path.dirname(file_path)

    # Python: tests/test_{basename}
    if ext == ".py":
        candidates = [
            os.path.join(project_dir, "tests", f"test_{basename}"),
            os.path.join(project_dir, dir_part, "tests", f"test_{basename}"),
        ]
    # JS/TS: same dir + .test.{ext} or .spec.{ext}
    elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
        candidates = [
            os.path.join(project_dir, dir_part, f"{name}.test{ext}"),
            os.path.join(project_dir, dir_part, f"{name}.spec{ext}"),
        ]
    else:
        # Generic: check tests/test_{name}{ext}
        candidates = [
            os.path.join(project_dir, "tests", f"test_{basename}"),
        ]

    return any(os.path.exists(c) for c in candidates)


def main() -> None:
    setup_crash_handler("test-generator-hook", fail_closed=False)

    payload = json_input()

    # Gate: feature flag
    if not get_feature_flag("TEST_GENERATION", default=False):
        sys.exit(0)

    # Gate: only file-modifying tools
    tool_name = payload.get("tool_name", "")
    if tool_name not in WRITE_TOOLS:
        sys.exit(0)

    # Extract file path (file_path or path)
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path") or tool_input.get("path", "")
    if not file_path:
        sys.exit(0)

    # Gate: skip test files
    if _is_test_file(file_path):
        sys.exit(0)

    # Check for corresponding test file
    project_dir = get_project_dir()
    if _find_corresponding_test(file_path, project_dir):
        sys.exit(0)

    # Inject suggestion
    suggestion = (
        f"No test file found for {file_path}. "
        "Consider running /OMG:testgen to generate tests."
    )
    json.dump({"additionalContext": suggestion}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
