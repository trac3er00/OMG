#!/usr/bin/env python3
"""
Stop Hook: Quality Gate Runner
Reads .oal/state/quality-gate.json and runs configured QA commands.
Blocks completion via JSON decision if any command fails.
Skips silently if config does not exist.

Callable API:
  check_quality_runner(data, project_dir) -> list[str]
    Returns list of block reasons (empty = pass).
"""
import json, sys, os, subprocess, shlex

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import _resolve_project_dir, should_skip_stop_hooks  # noqa: E402
from state_migration import resolve_state_file  # noqa: E402

STEPS = ["format", "lint", "typecheck", "test"]

# Security: whitelist of allowed command prefixes to prevent injection
# ONLY direct tool invocations are permitted — no script runners
ALLOWED_PREFIXES = [
    # JS/TS — test/lint/build ONLY (not arbitrary npm run/npx)
    ("npm", "test"),
    ("yarn", "test"),
    ("pnpm", "test"),
    ("bun", "test"),
    ("npx", "--no-install", "prettier"),
    ("npx", "--no-install", "eslint"),
    ("npx", "--no-install", "tsc"),
    ("npx", "--no-install", "jest"),
    ("npx", "--no-install", "vitest"),
    ("npx", "--no-install", "biome"),
    ("jest",),
    ("vitest",),
    ("eslint",),
    ("prettier",),
    ("tsc",),
    ("biome",),
    # Python
    ("pytest",),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("ruff",),
    ("mypy",),
    ("flake8",),
    ("black",),
    ("isort",),
    ("bandit",),
    ("pylint",),
    # Go
    ("go", "test"),
    ("go", "vet"),
    ("go", "build"),
    ("golangci-lint",),
    # Rust
    ("cargo", "test"),
    ("cargo", "check"),
    ("cargo", "build"),
    ("cargo", "clippy"),
    ("cargo", "fmt"),
    # Shell
    ("shellcheck",),
]

# Dangerous patterns that are NEVER allowed regardless of prefix
BLOCKED_PATTERNS = [
    "&&", "||", "|", ";", "`", "$(", "${", ">", "<", "\n",
    "rm ", "curl ", "wget ", "eval ", "exec ", "sudo ",
]


def is_safe_command(cmd):
    """Check if command matches whitelist and has no injection patterns."""
    cmd = cmd.strip()
    cmd_lower = cmd.lower()
    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        target = cmd_lower if any(ch.isalpha() for ch in pattern) else cmd
        if pattern in target:
            return False, f"blocked pattern '{pattern}'", []

    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        return False, f"invalid command syntax: {exc}", []
    if not argv:
        return False, "empty command", []

    # Check whitelist using token boundaries so `pytestx` cannot bypass.
    for prefix in ALLOWED_PREFIXES:
        if len(argv) < len(prefix):
            continue
        if tuple(argv[: len(prefix)]) == prefix:
            return True, "", argv
    return False, "not in allowed commands list", []


def check_quality_runner(data, project_dir):
    """Core quality-runner validation. Returns list of block-reason strings."""
    config_path = resolve_state_file(project_dir, "state/quality-gate.json", "quality-gate.json")

    if not os.path.exists(config_path):
        return []

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        return ["quality-gate.json is invalid JSON. Fix or delete it."]

    failures = []
    results = []

    for step in STEPS:
        cmd = config.get(step)
        if cmd is None or not isinstance(cmd, str) or not cmd.strip():
            results.append(f"SKIP {step} (not configured)")
            continue
        cmd = cmd.strip()

        # Security check
        safe, reason, argv = is_safe_command(cmd)
        if not safe:
            failures.append(step)
            results.append(f"BLOCKED {step}: '{cmd}' ({reason}). "
                          "Only standard dev tools allowed in quality-gate.json.")
            continue

        try:
            # Use argv-based execution (no shell interpretation).
            result = subprocess.run(
                argv,
                capture_output=True, text=True, timeout=60,
                cwd=project_dir
            )
            if result.returncode == 0:
                results.append(f"PASS {step}: {cmd} (exit 0)")
            else:
                failures.append(step)
                snippet = (result.stderr or result.stdout)[:300]
                results.append(f"FAIL {step}: {cmd} (exit {result.returncode})\n{snippet}")
        except subprocess.TimeoutExpired:
            failures.append(step)
            results.append(f"TIMEOUT {step}: {cmd}")
        except FileNotFoundError:
            results.append(f"SKIP {step}: command not found ({cmd})")

    if failures:
        msg = "Quality gate FAILED:\n" + "\n".join(results)
        msg += f"\n\nFailing: {', '.join(failures)}. Fix before completing."
        return [msg]

    # All passed -- print results as evidence to stderr
    if results:
        print("\n".join(results), file=sys.stderr)
    return []


# Standalone execution (backward compat: invoked directly by hook runner)
if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Skip if in a stop-hook loop or context-limited agent
    if should_skip_stop_hooks(data):
        sys.exit(0)

    project_dir = _resolve_project_dir()

    # Short-circuit: skip subprocess if context pressure is high
    _pressure_path = os.path.join(project_dir, ".oal", "state", ".context-pressure.json")
    try:
        if os.path.exists(_pressure_path):
            with open(_pressure_path, "r") as _f:
                _pressure = json.load(_f)
            if _pressure.get("is_high", False):
                print("[OAL quality-runner] Skipping subprocess checks: context pressure high", file=sys.stderr)
                sys.exit(0)
    except Exception:
        pass  # fail open — run checks if pressure file unreadable

    blocks = check_quality_runner(data, project_dir)
    if blocks:
        json.dump({"decision": "block", "reason": blocks[0]}, sys.stdout)
    sys.exit(0)
