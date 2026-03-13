#!/usr/bin/env python3
"""
Stop Hook: Test Validator (v5) — Enhanced Anti-Pattern Detection

v5 additions (T32):
  - Skip/ignore test detection (pytest.mark.skip, xit, xdescribe, etc.)
  - Mock-heavy test detection (ratio-based: mocks vs assertions)
  - Parameterized test gap detection (same function 3+ literal args)
  - Assertion-free Python test detection (def test_* with no assert)
  - Empty test body detection (pass, ..., comment-only)
  - Coverage metrics persistence to .omg/state/test-metrics.json

Callable API:
  check_test_quality(data, project_dir) -> list[str]
    Returns list of block reasons (empty = pass).
  analyze_test_content(content, filename) -> list[str]
    Returns list of issue strings for a single file's content.
  persist_metrics(project_dir, analysis) -> None
    Writes test quality metrics to .omg/state/test-metrics.json.
"""
import json, sys, os, re
from collections import Counter
from datetime import datetime, timezone

HOOKS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(HOOKS_DIR)
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from hooks._common import _resolve_project_dir, should_skip_stop_hooks

# --- Builtins excluded from parameterized-gap detection ---
_BUILTIN_FUNCS = frozenset({
    "test", "it", "describe", "print", "len", "range", "str", "int",
    "float", "list", "dict", "set", "tuple", "type", "isinstance",
    "assert_equal", "assertEqual", "patch", "mock", "Mock", "MagicMock",
    "expect", "require", "import", "open", "super", "getattr", "setattr",
    "hasattr", "sorted", "enumerate", "zip", "map", "filter", "min", "max",
})
_MUTATION_TOOLS = frozenset({"write", "edit", "multiedit", "bash"})


def analyze_test_content(content, filename="test.py"):
    """
    Analyze test file content for quality anti-patterns.

    Returns list of issue strings, each prefixed with a category label:
      FAKE:, BOILERPLATE:, HAPPY PATH ONLY:, EMPTY:, OVER-MOCKED:,
      SKIP:, ASSERTION-FREE:, MOCK-HEAVY:, PARAMETERIZED:
    """
    issues = []

    # === FAKE TEST PATTERNS (v3, kept) ===
    fake_patterns = [
        (r"expect\s*\(\s*true\s*\)\s*\.to(Be|Equal)\s*\(\s*true\s*\)", "assert true === true"),
        (r"expect\s*\(\s*1\s*\)\s*\.toBe\s*\(\s*1\s*\)", "assert 1 === 1"),
        (r"assert\s+True\b", "assert True (Python)"),
        (r"assert\s+1\s*==\s*1", "assert 1 == 1"),
    ]
    for pat, label in fake_patterns:
        if re.search(pat, content):
            issues.append(f"FAKE: {label}")

    # === BOILERPLATE-ONLY (v4, kept) ===
    type_checks = len(re.findall(
        r"(typeof\s+\w+|instanceof\s+\w+|toBeDefined|toBeInstanceOf|\.type\b)", content))
    behavior_checks = len(re.findall(
        r"(toEqual|toContain|toMatch|toThrow|rejects|resolves|toHaveBeenCalledWith|"
        r"toHaveProperty|toHaveLength|toBeGreaterThan|toBeLessThan|assert.*==|"
        r"assertEqual|assertIn|assertRaises|assert_called_with)", content))

    if type_checks > 3 and behavior_checks == 0:
        issues.append("BOILERPLATE: Only checks types/existence, never tests actual behavior")

    # === HAPPY PATH ONLY (v4, kept) ===
    has_error_tests = bool(re.search(
        r"(toThrow|rejects|assertRaises|error|invalid|empty|null|undefined|"
        r"edge.case|boundary|overflow|timeout|unauthorized|forbidden|not.found|"
        r"bad.request|missing|malformed)", content, re.IGNORECASE))
    test_count = len(re.findall(r"(test|it|describe)\s*\(", content))

    if test_count >= 3 and not has_error_tests:
        issues.append("HAPPY PATH ONLY: No error/edge case tests. "
                      "What happens with bad input? Unauthorized? Empty data?")

    # === NO ASSERTIONS — JS style (v3, kept) ===
    test_bodies = re.findall(
        r"(?:test|it)\s*\([^)]+,\s*(?:async\s*)?\(\)\s*=>\s*\{([^}]*)\}",
        content, re.DOTALL)
    for body in test_bodies:
        if body.strip() and not re.search(
            r"(expect|assert|should|verify|check|toBe|toEqual|toThrow|toHave)",
            body, re.IGNORECASE):
            issues.append("EMPTY: Test body has no assertions")
            break

    # === OVER-MOCKED (v3, kept) ===
    mock_count = len(re.findall(
        r"(jest\.mock|mock\(|patch\(|MagicMock|stub\(|sinon\.stub)", content))
    if mock_count > 5 and behavior_checks <= 1:
        issues.append("OVER-MOCKED: Heavy mocking but barely tests real behavior")

    # ============================================================
    # v5 NEW PATTERNS
    # ============================================================

    # === SKIP / IGNORE TESTS (v5) ===
    skip_patterns = [
        (r"@pytest\.mark\.skip", "@pytest.mark.skip"),
        (r"@pytest\.mark\.skipIf", "@pytest.mark.skipIf"),
        (r"@unittest\.skip", "@unittest.skip"),
        (r"\bit\.skip\s*\(", "it.skip()"),
        (r"\bdescribe\.skip\s*\(", "describe.skip()"),
        (r"\bxit\s*\(", "xit()"),
        (r"\bxdescribe\s*\(", "xdescribe()"),
    ]
    for pat, label in skip_patterns:
        if re.search(pat, content):
            issues.append(f"SKIP: {label} — skipped tests hide failures")

    # === ASSERTION-FREE Python tests (v5) ===
    _detect_assertion_free_python(content, issues)

    # === EMPTY TEST BODY — Python (v5) ===
    _detect_empty_python_test_body(content, issues)

    # === MOCK-HEAVY (v5, ratio-based refinement) ===
    # Different from OVER-MOCKED: catches moderate mock counts with poor assertion ratio
    assertion_count = len(re.findall(
        r"(\bassert\b|\bexpect\s*\(|\.should\b|\bverify\s*\()", content))
    if mock_count >= 3 and mock_count <= 5 and assertion_count < mock_count / 2:
        issues.append(
            f"MOCK-HEAVY: {mock_count} mocks but only {assertion_count} assertions "
            f"— tests should verify behavior, not just mock dependencies")

    # === PARAMETERIZED TEST GAP (v5) ===
    _detect_parameterized_gap(content, issues)

    return issues


def _extract_python_test_bodies(content):
    """
    Extract Python test function names and their body text.
    Returns list of (test_name, body_text) tuples.
    """
    results = []
    test_defs = list(re.finditer(r'def\s+(test_\w+)\s*\([^)]*\)\s*:', content))

    for idx, m in enumerate(test_defs):
        body_start = m.end()
        # Body extends to next def at same indent level, or EOF
        if idx + 1 < len(test_defs):
            body_end = test_defs[idx + 1].start()
        else:
            body_end = len(content)

        raw_body = content[body_start:body_end]
        # Keep only indented lines (the actual function body)
        body_lines = []
        for line in raw_body.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            if line and (line[0] == ' ' or line[0] == '\t'):
                body_lines.append(stripped)
            elif body_lines:
                # Non-indented non-empty line after body started = end of function
                break

        results.append((m.group(1), body_lines))

    return results


def _detect_assertion_free_python(content, issues):
    """Detect Python test functions with no assertion keywords."""
    for test_name, body_lines in _extract_python_test_bodies(content):
        if not body_lines:
            continue  # Empty bodies caught by _detect_empty_python_test_body
        body_text = ' '.join(body_lines)
        if not re.search(
            r'(\bassert\b|\bexpect\s*\(|\.should\b|\bverify\s*\()',
            body_text, re.IGNORECASE
        ):
            # Skip bodies that are just pass/ellipsis (caught by empty body detector)
            non_trivial = [l for l in body_lines
                           if l not in ('pass', '...') and not l.startswith('#')]
            if non_trivial:
                issues.append(
                    f"ASSERTION-FREE: {test_name} has no assertions")


def _detect_empty_python_test_body(content, issues):
    """Detect Python test functions with empty bodies (pass, ..., comment-only)."""
    for test_name, body_lines in _extract_python_test_bodies(content):
        non_trivial = [l for l in body_lines
                       if l not in ('pass', '...') and not l.startswith('#')]
        if not non_trivial:
            issues.append(f"EMPTY: {test_name} has empty body (only pass/ellipsis/comments)")


def _detect_parameterized_gap(content, issues):
    """
    Detect functions called 3+ times with different literal arguments,
    suggesting @pytest.mark.parametrize would be more appropriate.
    """
    # Find function calls with literal arguments (numbers or strings)
    calls = re.findall(
        r'\b(\w+)\s*\(\s*(\d+(?:\.\d+)?|"[^"]*"|\'[^\']*\')\s*(?:\)|,)',
        content)

    # Group by function name, collect unique literal args
    call_groups = {}
    for func, arg in calls:
        if func.lower() not in _BUILTIN_FUNCS:
            call_groups.setdefault(func, set()).add(arg)

    for func, args in call_groups.items():
        if len(args) >= 3:
            issues.append(
                f"PARAMETERIZED: '{func}' called with {len(args)} different "
                f"literal values — consider @pytest.mark.parametrize or "
                f"@pytest.mark.parametrize")


def persist_metrics(project_dir, analysis):
    """
    Write test quality metrics to .omg/state/test-metrics.json.

    Args:
        project_dir: Project root directory.
        analysis: Dict with keys: total_tests, fake_count, boilerplate_count,
                  edge_case_count, skip_count, assertion_free_count.
    """
    try:
        state_dir = os.path.join(project_dir, ".omg", "state")
        os.makedirs(state_dir, exist_ok=True)

        total = analysis.get("total_tests", 0)
        issue_sum = (
            analysis.get("fake_count", 0)
            + analysis.get("boilerplate_count", 0)
            + analysis.get("skip_count", 0)
            + analysis.get("assertion_free_count", 0)
        )

        # Quality score: 1.0 = perfect, 0.0 = all tests problematic
        if total > 0:
            quality_score = round(max(0.0, 1.0 - (issue_sum / total)), 3)
        else:
            quality_score = 1.0

        metrics = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_tests": analysis.get("total_tests", 0),
            "fake_count": analysis.get("fake_count", 0),
            "boilerplate_count": analysis.get("boilerplate_count", 0),
            "edge_case_count": analysis.get("edge_case_count", 0),
            "skip_count": analysis.get("skip_count", 0),
            "assertion_free_count": analysis.get("assertion_free_count", 0),
            "quality_score": quality_score,
        }

        metrics_path = os.path.join(state_dir, "test-metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, separators=(",", ":"))
    except Exception:
        pass  # Crash isolation: never fail the hook


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
    # Aggregate metrics across all files
    agg = {
        "total_tests": 0, "fake_count": 0, "boilerplate_count": 0,
        "edge_case_count": 0, "skip_count": 0, "assertion_free_count": 0,
    }

    for tf in test_files:
        try:
            with open(tf, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        filename = os.path.basename(tf)
        issues = analyze_test_content(content, filename)

        # Count tests in this file
        py_tests = len(re.findall(r'def\s+test_\w+\s*\(', content))
        js_tests = len(re.findall(r'(test|it)\s*\(', content))
        agg["total_tests"] += py_tests + js_tests

        # Count issue categories
        for issue in issues:
            if issue.startswith("FAKE:"):
                agg["fake_count"] += 1
            elif issue.startswith("BOILERPLATE:"):
                agg["boilerplate_count"] += 1
            elif "HAPPY PATH" in issue:
                agg["edge_case_count"] += 1
            elif issue.startswith("SKIP:"):
                agg["skip_count"] += 1
            elif issue.startswith("ASSERTION-FREE:"):
                agg["assertion_free_count"] += 1

        if issues:
            warnings.append(f"{filename}: " + "; ".join(issues))

    # Persist metrics
    try:
        persist_metrics(project_dir, agg)
    except Exception:
        pass

    if warnings:
        msg = "TEST QUALITY ISSUES:\n" + "\n".join(f"  {w}" for w in warnings)
        msg += ("\n\nTests should verify what USERS need, not just that code exists.\n"
                "Ask: 'What does the user expect to happen? What could go wrong?'\n"
                "Write tests for those scenarios.")
        return [msg]

    return []


def check_methodology_contract(data):
    if not isinstance(data, dict):
        return []

    tool_name = str(data.get("tool_name", "")).strip().lower()
    if tool_name not in _MUTATION_TOOLS:
        return []

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return ["METHODOLOGY: mutation-capable flow requires metadata with done_when criteria"]

    exemption = str(tool_input.get("exemption", "")).strip().lower()
    if exemption == "docs":
        return []

    metadata = tool_input.get("metadata")
    if not isinstance(metadata, dict):
        return ["METHODOLOGY: mutation-capable flow requires metadata with done_when criteria"]

    done_when = metadata.get("done_when")
    if isinstance(done_when, str) and done_when.strip():
        return []
    if isinstance(done_when, list):
        if any(str(item).strip() for item in done_when):
            return []
    if isinstance(done_when, dict):
        criteria = done_when.get("criteria")
        if isinstance(criteria, str) and criteria.strip():
            return []
        if isinstance(criteria, list) and any(str(item).strip() for item in criteria):
            return []
        if str(done_when.get("summary", "")).strip():
            return []

    return ["METHODOLOGY: done_when criteria required before mutation-capable execution"]


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
    blocks.extend(check_methodology_contract(data))
    if blocks:
        json.dump({"decision": "block", "reason": blocks[0]}, sys.stdout)
    sys.exit(0)
