#!/usr/bin/env python3
"""Unified PostToolUse dispatcher — runs all post-tool hooks in one process.

Replaces separate subprocess invocations of circuit-breaker.py, tool-ledger.py,
budget_governor.py, and test_generator_hook.py with a single process.

All PostToolUse hooks are fail-open (observational, never block).
Hook order:
1. tool-ledger.py        — Record tool usage to ledger
2. circuit-breaker.py    — Track failure patterns
3. budget_governor.py    — Cost tracking + budget alerts
4. test_generator_hook.py — Test suggestion after file writes
"""
from __future__ import annotations

import importlib.util
import json
import io
import os
import sys
from pathlib import Path

HOOKS_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(HOOKS_DIR).parent)
PORTABLE_RUNTIME_ROOT = str(Path(PROJECT_ROOT) / "omg-runtime")
for path in (HOOKS_DIR, PROJECT_ROOT, PORTABLE_RUNTIME_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from _common import bootstrap_runtime_paths, setup_crash_handler, json_input

bootstrap_runtime_paths(__file__)
setup_crash_handler("post-tool-all", fail_closed=False)

data = json_input()
tool_name = data.get("tool_name", "")
combined_context = []


def _run_hook_safely(module_name: str, filename: str) -> str | None:
    """Run a PostToolUse hook module, capturing additionalContext output.

    Returns the additionalContext string if emitted, else None.
    All errors are swallowed (fail-open).
    """
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    captured = io.StringIO()

    try:
        sys.stdin = io.StringIO(json.dumps(data))
        sys.stdout = captured

        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(HOOKS_DIR, filename)
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except SystemExit:
                pass
    except Exception as e:
        print(f"[OMG] post-tool-all: {module_name} error: {e}", file=sys.stderr)
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout

    output = captured.getvalue().strip()
    if output:
        try:
            parsed = json.loads(output)
            ctx = parsed.get("hookSpecificOutput", {}).get("additionalContext", "")
            if ctx:
                return ctx
        except json.JSONDecodeError:
            pass
    return None


# --- Dispatch all hooks (fail-open, order matters for context aggregation) ---

# 1. Tool ledger (all tools)
_run_hook_safely("tool-ledger", "tool-ledger.py")

# 2. Circuit breaker (Bash only — tracks command failures)
if tool_name == "Bash":
    _run_hook_safely("circuit-breaker", "circuit-breaker.py")

# 3. Budget governor (all tools — cost tracking)
ctx = _run_hook_safely("budget_governor", "budget_governor.py")
if ctx:
    combined_context.append(ctx)

# 4. Test generator (Write/Edit/MultiEdit only)
if tool_name in ("Write", "Edit", "MultiEdit"):
    ctx = _run_hook_safely("test_generator_hook", "test_generator_hook.py")
    if ctx:
        combined_context.append(ctx)

# Emit combined additionalContext
if combined_context:
    json.dump({
        "hookSpecificOutput": {
            "additionalContext": "\n".join(combined_context),
        }
    }, sys.stdout)

sys.exit(0)
