#!/usr/bin/env python3
"""Unified PreToolUse dispatcher — runs all pre-tool hooks in one process.

Replaces separate subprocess invocations of firewall.py, secret-guard.py,
and pre-tool-inject.py with a single process that dispatches by tool type.

Hook order (security-first):
1. firewall.py      — Bash commands: destructive ops, SSRF, pipe-to-shell
2. secret-guard.py  — File access: .env, secrets, path traversal
3. pre-tool-inject.py — Plan reminder injection (non-blocking)

If any security hook denies, the denial is emitted immediately and later
hooks are skipped. This preserves fail-closed behavior.
"""
from __future__ import annotations

import importlib
import json
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
setup_crash_handler("pre-tool-all", fail_closed=True)

data = json_input()
tool_name = data.get("tool_name", "")


def _run_hook_module(module_name: str) -> dict | None:
    """Import and run a hook module, capturing its stdout output.

    Returns the parsed JSON output if the hook emitted a decision, else None.
    The hook modules use sys.exit(0) to indicate "no decision" (allow),
    which we catch and treat as None.
    """
    import io
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    captured = io.StringIO()

    try:
        # Re-provide stdin data for the hook module
        sys.stdin = io.StringIO(json.dumps(data))
        sys.stdout = captured

        # Import and execute the module
        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(HOOKS_DIR, f"{module_name}.py")
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except SystemExit:
                pass  # Hooks call sys.exit(0) to indicate "allow"
    except Exception as e:
        print(f"[OMG] pre-tool-all: {module_name} error: {e}", file=sys.stderr)
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout

    output = captured.getvalue().strip()
    if output:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass
    return None


# --- Dispatch ---

# 1. Firewall (Bash only)
if tool_name == "Bash":
    result = _run_hook_module("firewall")
    if result:
        # Check if it's a deny decision
        hook_output = result.get("hookSpecificOutput", {})
        if hook_output.get("permissionDecision") == "deny":
            json.dump(result, sys.stdout)
            sys.exit(0)

# 2. Secret guard (file access tools)
if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
    result = _run_hook_module("secret-guard")
    if result:
        hook_output = result.get("hookSpecificOutput", {})
        if hook_output.get("permissionDecision") == "deny":
            json.dump(result, sys.stdout)
            sys.exit(0)
        # Non-deny decisions (ask) are also emitted
        json.dump(result, sys.stdout)
        sys.exit(0)

# 3. Pre-tool inject (all tools, non-blocking)
result = _run_hook_module("pre-tool-inject")
if result:
    json.dump(result, sys.stdout)

sys.exit(0)
