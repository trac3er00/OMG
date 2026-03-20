"""Verify that policy_engine regex correctly distinguishes catastrophic rm
from legitimate project-scoped rm operations.

Layer architecture:
  Layer 1 (settings deny glob): coarse, always checked first by Claude Code
  Layer 2 (policy_engine regex): precise, checked by firewall hook
  Layer 3 (hooks): context-aware (bypass mode, mutation gate)

The settings glob `Bash(rm -rf /*)` is TOO BROAD — it blocks any rm -rf
with an absolute path.  We remove it from settings and rely on
policy_engine's regex which correctly distinguishes:
  - `rm -rf /`  → DENY  (catastrophic: deletes root)
  - `rm -rf /*` → DENY  (catastrophic: deletes all root dirs)
  - `rm -rf /Users/.../dist/` → ALLOW (legitimate project cleanup)
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.expanduser("~/.claude/hooks"))
sys.path.insert(0, os.path.expanduser("~/.claude"))
os.environ.setdefault(
    "CLAUDE_PROJECT_DIR",
    os.path.join(os.path.dirname(__file__), "..", ".."),
)

from policy_engine import evaluate_bash_command, DESTRUCT_PATTERNS


# --- Catastrophic commands: MUST be denied ---

CATASTROPHIC = [
    "rm -rf /",
    "rm -rf / ",
    "rm -fr /",
    "rm -rfi /",
    "rm -rf ~",
    "rm -rf ~/",
    "rm -rf $HOME",
    "rm -rf ${HOME}",
    "rm -rf ..",
]


@pytest.mark.parametrize("cmd", CATASTROPHIC)
def test_catastrophic_rm_denied(cmd):
    result = evaluate_bash_command(cmd)
    assert result.action == "deny", (
        f"{cmd!r} must be denied but got {result.action}: {result.reason}"
    )


# --- Legitimate project rm: MUST be allowed ---

LEGITIMATE = [
    "rm -rf /Users/cminseo/Documents/scripts/Shell/OMG/dist/dist/",
    "rm -rf /tmp/build/",
    "rm -rf /home/user/project/node_modules/",
    "rm -rf ./dist/",
    "rm -rf dist/",
    "rm -rf build/output/",
    "rm -rf /Users/cminseo/.cache/pip/",
    "rm -rf /var/folders/tmp/pytest-1234/",
]


@pytest.mark.parametrize("cmd", LEGITIMATE)
def test_legitimate_rm_allowed(cmd):
    result = evaluate_bash_command(cmd)
    assert result.action == "allow", (
        f"{cmd!r} should be allowed but got {result.action}: {result.reason}"
    )


# --- Glob wildcard variants: MUST be denied ---

GLOB_CATASTROPHIC = [
    "rm -rf /*",
    "rm -rf ~/*",
]


@pytest.mark.parametrize("cmd", GLOB_CATASTROPHIC)
def test_glob_wildcard_rm_denied(cmd):
    result = evaluate_bash_command(cmd)
    assert result.action == "deny", (
        f"{cmd!r} must be denied but got {result.action}: {result.reason}"
    )


def test_regex_precision_summary():
    """Verify the regex distinguishes / (root) from /specific/path."""
    root_pattern = DESTRUCT_PATTERNS[0][0]  # rm -rf / pattern
    # Must match: rm -rf / (end of string or whitespace or *)
    assert re.search(root_pattern, "rm -rf /")
    # Must NOT match: rm -rf /specific/path
    assert not re.search(root_pattern, "rm -rf /Users/cminseo/project/dist/")
    assert not re.search(root_pattern, "rm -rf /tmp/build")
