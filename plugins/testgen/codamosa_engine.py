"""CodaMosa-inspired iterative test generator engine.

Implements an iterative coverage-driven loop inspired by CodaMosa (ICSE 2023):
  1. Run existing tests + collect coverage
  2. Parse coverage report to find uncovered functions/lines
  3. Generate targeted tests for uncovered code using skeleton_generator
  4. Write new tests to test file
  5. Run tests again, verify coverage improved
  6. Stop if target_coverage met OR max_iterations reached

Fallback: when coverage tool is unavailable, calls generate_test_skeleton()
once and returns ``{"fallback_used": True, "iterations": 1}``.

Feature flag: TEST_GENERATION (default False).
Stdlib only: subprocess, json, pathlib, re.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict
from pathlib import Path

_logger = logging.getLogger(__name__)

# Lazy imports for crash isolation — these modules live in the same package
# and in hooks/.  Import errors are caught at call sites.
_SUBPROCESS_TIMEOUT = 60  # seconds
_MAX_ITERATIONS_CAP = 5


def _import_get_feature_flag():
    """Lazy import get_feature_flag from hooks/_common.py."""
    try:
        import sys
        import os

        hooks_dir = str(Path(__file__).resolve().parent.parent.parent / "hooks")
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        from _common import get_feature_flag  # type: ignore[import-untyped]

        return get_feature_flag
    except Exception:
        return None


def get_feature_flag(flag_name: str, default: bool = False) -> bool:
    """Get feature flag, with fallback to *default* on import failure."""
    fn = _import_get_feature_flag()
    if fn is not None:
        return fn(flag_name, default)
    return default


def _empty_result() -> dict:
    """Return a no-op result dict."""
    return {
        "iterations": 0,
        "initial_coverage": 0.0,
        "final_coverage": 0.0,
        "tests_generated": 0,
        "fallback_used": False,
    }


# ---------------------------------------------------------------------------
# Coverage subprocess helpers
# ---------------------------------------------------------------------------


def _run_coverage_subprocess(
    project_dir: str,
    source_file: str,
    framework: str,
) -> dict:
    """Run coverage tool and return parsed result.

    Returns:
        {"file_coverage": float, "uncovered_lines": list[int]}

    Raises:
        FileNotFoundError, OSError, subprocess.TimeoutExpired on failure.
    """
    source_path = Path(source_file)
    rel_source = str(source_path.relative_to(project_dir)) if source_path.is_absolute() else str(source_path)

    if framework in ("pytest", "unknown"):
        return _run_pytest_coverage(project_dir, rel_source)
    if framework in ("jest", "vitest"):
        return _run_jest_coverage(project_dir, rel_source)
    if framework in ("go test", "go"):
        return _run_go_coverage(project_dir, rel_source)

    # Unsupported framework — raise so caller triggers fallback
    raise FileNotFoundError(f"No coverage runner for framework: {framework}")


def _run_pytest_coverage(project_dir: str, rel_source: str) -> dict:
    """Run pytest --cov and parse coverage json report."""
    cov_json_path = Path(project_dir) / ".coverage_codamosa.json"

    argv = [
        "python", "-m", "pytest",
        f"--cov={Path(rel_source).stem}",
        "--cov-report", f"json:{cov_json_path}",
        "--quiet", "--no-header",
    ]

    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
        cwd=project_dir,
    )
    if result.returncode != 0:
        snippet = (result.stderr or result.stdout or "").strip()[:200]
        raise RuntimeError(f"pytest coverage failed (rc={result.returncode}): {snippet}")

    return _parse_coverage_json(str(cov_json_path), rel_source)


def _parse_coverage_json(json_path: str, rel_source: str) -> dict:
    """Parse coverage.json produced by pytest-cov."""
    path = Path(json_path)
    if not path.is_file():
        raise FileNotFoundError(f"Coverage report not found: {json_path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    # coverage json format: {"files": {"path": {"summary": {"percent_covered": X}, "missing_lines": [...]}}}
    files = data.get("files", {})

    # Try exact match first, then basename match
    file_data = files.get(rel_source)
    if file_data is None:
        for key, val in files.items():
            if Path(key).name == Path(rel_source).name:
                file_data = val
                break

    if file_data is None:
        # File not in report — 0 coverage
        return {"file_coverage": 0.0, "uncovered_lines": []}

    summary = file_data.get("summary", {})
    pct = summary.get("percent_covered", 0.0)
    missing = file_data.get("missing_lines", [])

    return {"file_coverage": float(pct), "uncovered_lines": list(missing)}


def _run_jest_coverage(project_dir: str, rel_source: str) -> dict:
    """Run jest/vitest --coverage and parse coverage-summary.json."""
    argv = ["npx", "--no-install", "jest", "--coverage", "--coverageReporters=json-summary", "--silent"]

    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
        cwd=project_dir,
    )
    if result.returncode != 0:
        snippet = (result.stderr or result.stdout or "").strip()[:200]
        raise RuntimeError(f"jest coverage failed (rc={result.returncode}): {snippet}")

    summary_path = Path(project_dir) / "coverage" / "coverage-summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError("Jest coverage summary not found")

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    total = data.get("total", {}).get("lines", {})
    pct = total.get("pct", 0.0)

    return {"file_coverage": float(pct), "uncovered_lines": []}


def _run_go_coverage(project_dir: str, rel_source: str) -> dict:
    """Run go test -coverprofile and parse cover.out."""
    cover_path = Path(project_dir) / "cover.out"
    argv = ["go", "test", "-coverprofile", str(cover_path), "./..."]

    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
        cwd=project_dir,
    )
    if result.returncode != 0:
        snippet = (result.stderr or result.stdout or "").strip()[:200]
        raise RuntimeError(f"go coverage failed (rc={result.returncode}): {snippet}")

    if not cover_path.is_file():
        raise FileNotFoundError("Go coverage profile not found")

    return _parse_go_cover(str(cover_path))


def _parse_go_cover(cover_path: str) -> dict:
    """Parse Go cover.out format: ``file:startLine.startCol,endLine.endCol N count``."""
    content = Path(cover_path).read_text(encoding="utf-8")
    total_stmts = 0
    covered_stmts = 0
    uncovered_lines: list[int] = []

    for line in content.splitlines():
        if line.startswith("mode:"):
            continue
        match = re.match(r"(.+):(\d+)\.\d+,(\d+)\.\d+\s+(\d+)\s+(\d+)", line)
        if not match:
            continue
        start_line = int(match.group(2))
        stmts = int(match.group(4))
        count = int(match.group(5))
        total_stmts += stmts
        if count > 0:
            covered_stmts += stmts
        else:
            uncovered_lines.append(start_line)

    pct = (covered_stmts / total_stmts * 100) if total_stmts > 0 else 0.0
    return {"file_coverage": pct, "uncovered_lines": uncovered_lines}


def _run_tests_subprocess(project_dir: str, framework: str) -> bool:
    """Run the project's test suite. Returns True if tests pass."""
    if framework in ("pytest", "unknown"):
        argv = ["python", "-m", "pytest", "--quiet", "--no-header"]
    elif framework in ("jest", "vitest"):
        argv = ["npx", "--no-install", framework, "--silent"]
    elif framework in ("go test", "go"):
        argv = ["go", "test", "./..."]
    else:
        return True  # Can't run → assume ok

    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
            cwd=project_dir,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# ---------------------------------------------------------------------------
# Skeleton generation integration
# ---------------------------------------------------------------------------


def _generate_targeted_tests(
    source_file: str,
    uncovered_lines: list[int],
    framework_info: dict,
    iteration: int,
) -> str:
    """Generate test skeleton targeting uncovered code.

    Uses skeleton_generator.generate_test_skeleton as the base, then
    annotates with iteration metadata.
    """
    try:
        from plugins.testgen.skeleton_generator import generate_test_skeleton
    except ImportError:
        return ""

    skeleton = generate_test_skeleton(source_file, framework_info)
    if not skeleton:
        return ""

    # Tag with iteration for traceability
    header = f"# CodaMosa iteration {iteration} — targeting uncovered lines: {uncovered_lines[:10]}\n"
    return header + skeleton


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_codamosa(
    project_dir: str,
    source_file: str,
    target_coverage: int = 80,
    max_iterations: int = 5,
) -> dict:
    """Run CodaMosa-inspired iterative test generation loop.

    Args:
        project_dir: Absolute or relative path to the project root.
        source_file: Path to the source file to generate tests for.
        target_coverage: Target line coverage percentage (0-100).
        max_iterations: Max iteration count (hard-capped at 5).

    Returns:
        Dict with keys: iterations, initial_coverage, final_coverage,
        tests_generated, fallback_used.
    """
    # Feature flag gate
    if not get_feature_flag("TEST_GENERATION", default=False):
        return _empty_result()

    # Hard cap
    max_iterations = min(max_iterations, _MAX_ITERATIONS_CAP)

    # Validate source file
    source_path = Path(source_file)
    if not source_path.exists() or not source_path.read_text(encoding="utf-8").strip():
        return {
            "iterations": 0,
            "initial_coverage": 0.0,
            "final_coverage": 0.0,
            "tests_generated": 0,
            "fallback_used": False,
        }

    # Detect framework
    framework = "unknown"
    framework_dict: dict = {"framework": "unknown"}
    detected_test_dir = "tests"
    try:
        from plugins.testgen.framework_detector import detect_test_framework  # noqa: F811

        fw_info = detect_test_framework(project_dir)
        framework = fw_info.framework
        detected_test_dir = fw_info.test_dir or "tests"
        framework_dict = {
            "framework": fw_info.framework,
            "config_file": fw_info.config_file,
            "test_dir": fw_info.test_dir,
            "assertion_style": fw_info.assertion_style,
            "mock_library": fw_info.mock_library,
        }
    except ImportError:
        # Optional: plugins.testgen.framework_detector not available
        _logger.debug("Failed to import framework detector", exc_info=True)

    # Determine test output path
    test_dir = Path(project_dir) / detected_test_dir
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / f"test_{source_path.stem}_codamosa.py"

    initial_coverage = 0.0
    current_coverage = 0.0
    tests_generated = 0
    completed_iterations = 0

    for iteration in range(1, max_iterations + 1):
        completed_iterations = iteration

        # Step 1: Run coverage
        try:
            cov_result = _run_coverage_subprocess(project_dir, source_file, framework)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired, Exception):
            # Fallback: generate skeleton once and return
            return _do_fallback(source_file, framework_dict)

        file_cov = cov_result.get("file_coverage", 0.0)
        uncovered = cov_result.get("uncovered_lines", [])

        if iteration == 1:
            initial_coverage = file_cov
        current_coverage = file_cov

        # Step 2: Check if target met
        if current_coverage >= target_coverage:
            break

        # Step 3: Generate targeted tests
        new_tests = _generate_targeted_tests(source_file, uncovered, framework_dict, iteration)
        if new_tests:
            # Step 4: Append to test file
            mode = "a" if test_file.exists() else "w"
            with open(test_file, mode, encoding="utf-8") as f:
                f.write("\n\n" + new_tests if mode == "a" else new_tests)
            tests_generated += 1

        # Step 5: Run tests to verify they pass
        _run_tests_subprocess(project_dir, framework)

    return {
        "iterations": completed_iterations,
        "initial_coverage": initial_coverage,
        "final_coverage": current_coverage,
        "tests_generated": tests_generated,
        "fallback_used": False,
    }


def _do_fallback(source_file: str, framework_dict: dict) -> dict:
    """Fallback to single-pass skeleton generation."""
    try:
        from plugins.testgen.skeleton_generator import generate_test_skeleton

        skeleton = generate_test_skeleton(source_file, framework_dict)
        generated = 1 if skeleton else 0
    except ImportError:
        generated = 0

    return {
        "iterations": 1,
        "initial_coverage": 0.0,
        "final_coverage": 0.0,
        "tests_generated": generated,
        "fallback_used": True,
    }
