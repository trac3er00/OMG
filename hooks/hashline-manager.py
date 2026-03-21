#!/usr/bin/env python3
"""Unified hashline manager — dispatches to injector, validator, or formatter-bridge.

Consolidates the three hashline hooks into a single entry point:
- inject: PreToolUse(Read) — inject hashlines into file content
- validate: PreToolUse(Edit) — validate hashline references in edits
- format: PostToolUse(Write/Edit) — reconcile hashlines after formatting

All operations are feature-gated on OMG_HASHLINE_ENABLED.
"""
from __future__ import annotations

import importlib.util
import json
import io
import os
import sys
from pathlib import Path

HOOKS_DIR = str(Path(__file__).resolve().parent)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import setup_crash_handler, json_input, get_feature_flag

setup_crash_handler("hashline-manager", fail_closed=False)

# Feature gate
if not get_feature_flag("HASHLINE", default=False):
    sys.exit(0)

data = json_input()
tool_name = data.get("tool_name", "")
hook_event = os.environ.get("CLAUDE_HOOK_EVENT", "PreToolUse")


def _dispatch(filename: str) -> None:
    """Run a hashline sub-hook, passing through stdin/stdout."""
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    captured = io.StringIO()

    try:
        sys.stdin = io.StringIO(json.dumps(data))
        sys.stdout = captured

        spec = importlib.util.spec_from_file_location(
            filename.replace(".py", "").replace("-", "_"),
            os.path.join(HOOKS_DIR, filename),
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except SystemExit:
                pass
    except Exception as e:
        print(f"[OMG] hashline-manager: {filename} error: {e}", file=sys.stderr)
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout

    output = captured.getvalue().strip()
    if output:
        print(output)


# Dispatch based on tool type and hook event
if hook_event == "PreToolUse":
    if tool_name == "Read":
        _dispatch("hashline-injector.py")
    elif tool_name in ("Edit", "MultiEdit"):
        _dispatch("hashline-validator.py")
elif hook_event == "PostToolUse":
    if tool_name in ("Write", "Edit", "MultiEdit"):
        _dispatch("hashline-formatter-bridge.py")

sys.exit(0)
