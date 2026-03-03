#!/usr/bin/env python3
"""
Stop Hook: Test Validator (v4) — User-Journey Focused
Catches not just fake tests, but MEANINGLESS tests.

v4 additions:
  - Detects "boilerplate-only" test files (only testing existence/types)
  - Checks if tests align with user stories / working-memory gomgs
  - Warns when tests only cover happy path

Callable API:
  check_test_quality(data, project_dir) -> list[str]
    Returns list of block reasons (empty = pass).
"""
import json, sys, os, re

HOOKS_DIR = os.path.dirname(__file__)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import _resolve_project_dir, should_skip_stop_hooks


def check_test_quality(data, project_dir):
    """Core test-quality validation. Returns list of block-reason strings."""
    import subprocess

    # Find recently modified test files
    test_files = []
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=AM"],
            capture_output=True, text=True, timeout=10, cwd=project_dir
        )
        for f in result.stdout.strip().split("\n"):
            if f and any(p in f.lower() for p in
                         [".test.", ".spec.", "_test.", "test_", "__tests__", ".tests."]):
                full = os.path.join(project_dir, f)
                if os.path.exists(full):
                    test_files.append(full)
    except Exception:
        pass

    if not test_files:
        return []

    warnings = []

    for tf in test_files:
        try:
            with open(tf, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        filename = os.path.basename(tf)
        issues = []

        # === FAKE TEST PATTERNS (from v3, kept) ===
        fake_patterns = [
            (r"expect\s*\(\s*true\s*\)\s*\.to(Be|Equal)\s*\(\s*true\s*\)", "assert true === true"),
            (r"expect\s*\(\s*1\s*\)\s*\.toBe\s*\(\s*1\s*\)", "assert 1 === 1"),
            (r"assert\s+True\b", "assert True (Python)"),
            (r"assert\s+1\s*==\s*1", "assert 1 == 1"),
        ]
        for pat, label in fake_patterns:
            if re.search(pat, content):
                issues.append(f"FAKE: {label}")

        # === BOILERPLATE-ONLY (v4 new) ===
        # Tests that only check typeof/instanceof/existence
        type_checks = len(re.findall(
            r"(typeof\s+\w+|instanceof\s+\w+|toBeDefined|toBeInstanceOf|\.type\b)", content))
        behavior_checks = len(re.findall(
            r"(toEqual|toContain|toMatch|toThrow|rejects|resolves|toHaveBeenCalledWith|"
            r"toHaveProperty|toHaveLength|toBeGreaterThan|toBeLessThan|assert.*==|"
            r"assertEqual|assertIn|assertRaises|assert_called_with)", content))

        if type_checks > 3 and behavior_checks == 0:
            issues.append("BOILERPLATE: Only checks types/existence, never tests actual behavior")

        # === HAPPY PATH ONLY (v4 new) ===
        # Check for error/edge case testing
        has_error_tests = bool(re.search(
            r"(toThrow|rejects|assertRaises|error|invalid|empty|null|undefined|"
            r"edge.case|boundary|overflow|timeout|unauthorized|forbidden|not.found|"
            r"bad.request|missing|malformed)", content, re.IGNORECASE))
        test_count = len(re.findall(r"(test|it|describe)\s*\(", content))

        if test_count >= 3 and not has_error_tests:
            issues.append("HAPPY PATH ONLY: No error/edge case tests. "
                          "What happens with bad input? Unauthorized? Empty data?")

        # === NO ASSERTIONS (v3 kept) ===
        test_bodies = re.findall(
            r"(?:test|it)\s*\([^)]+,\s*(?:async\s*)?\(\)\s*=>\s*\{([^}]*)\}",
            content, re.DOTALL)
        for body in test_bodies:
            if body.strip() and not re.search(
                r"(expect|assert|should|verify|check|toBe|toEqual|toThrow|toHave)",
                body, re.IGNORECASE):
                issues.append("EMPTY: Test body has no assertions")
                break

        # === MOCK EVERYTHING (v3 kept, improved) ===
        mock_count = len(re.findall(r"(jest\.mock|mock\(|patch\(|MagicMock|stub\(|sinon\.stub)", content))
        if mock_count > 5 and behavior_checks <= 1:
            issues.append("OVER-MOCKED: Heavy mocking but barely tests real behavior")

        if issues:
            warnings.append(f"{filename}: " + "; ".join(issues))

    if warnings:
        msg = "TEST QUALITY ISSUES:\n" + "\n".join(f"  {w}" for w in warnings)
        msg += ("\n\nTests should verify what USERS need, not just that code exists.\n"
                "Ask: 'What does the user expect to happen? What could go wrong?'\n"
                "Write tests for those scenarios.")
        return [msg]

    return []


# Standalone execution (backward compat: invoked directly by hook runner)
if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if should_skip_stop_hooks(data):
        sys.exit(0)


    project_dir = _resolve_project_dir()
    blocks = check_test_quality(data, project_dir)
    if blocks:
        json.dump({"decision": "block", "reason": blocks[0]}, sys.stdout)
    sys.exit(0)
