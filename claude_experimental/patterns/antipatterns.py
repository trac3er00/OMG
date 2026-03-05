"""Anti-pattern detection and code quality scoring for Python source files.

Detects common anti-patterns via AST analysis and regex heuristics,
then produces a 0.0–1.0 quality score based on severity-weighted violations.

Feature-flag gated: OMG_PATTERN_INTELLIGENCE_ENABLED=1
"""
from __future__ import annotations

import ast
import os
import re
import tokenize
import io
from dataclasses import dataclass, field
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AntiPatternViolation:
    """A single anti-pattern violation found in source code."""

    rule_name: str
    severity: str  # critical | high | medium | low
    line: int
    description: str
    snippet: str


# Severity weights used for quality scoring
_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 0.3,
    "high": 0.2,
    "medium": 0.1,
    "low": 0.05,
}

# Maximum total weighted violations before score bottoms out at 0.0
_MAX_VIOLATIONS_WEIGHT = 1.5

# Type alias for custom rule functions
RuleFn = Callable[[str, str], list[AntiPatternViolation]]


# ---------------------------------------------------------------------------
# Built-in detectors (AST-based)
# ---------------------------------------------------------------------------

def _detect_bare_except(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect bare ``except:`` without a specific exception type."""
    violations: list[AntiPatternViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            lineno = node.lineno
            snippet = lines[lineno - 1].rstrip() if lineno <= len(lines) else ""
            violations.append(AntiPatternViolation(
                rule_name="bare_except",
                severity="high",
                line=lineno,
                description="Bare 'except:' catches all exceptions including KeyboardInterrupt and SystemExit",
                snippet=snippet,
            ))
    return violations


def _detect_mutable_defaults(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect mutable default arguments (list, dict, set literals) in function signatures."""
    violations: list[AntiPatternViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()
    mutable_types = (ast.List, ast.Dict, ast.Set)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if default is not None and isinstance(default, mutable_types):
                    lineno = default.lineno
                    snippet = lines[lineno - 1].rstrip() if lineno <= len(lines) else ""
                    violations.append(AntiPatternViolation(
                        rule_name="mutable_default",
                        severity="high",
                        line=lineno,
                        description="Mutable default argument; use None and create inside function body",
                        snippet=snippet,
                    ))
    return violations


def _detect_god_class(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect god classes with >20 methods or >500 lines."""
    violations: list[AntiPatternViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            method_count = sum(
                1 for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            end_lineno = getattr(node, "end_lineno", None)
            class_lines = (end_lineno - node.lineno + 1) if end_lineno else 0
            reasons: list[str] = []
            if method_count > 20:
                reasons.append(f"{method_count} methods (>20)")
            if class_lines > 500:
                reasons.append(f"{class_lines} lines (>500)")
            if reasons:
                snippet = lines[node.lineno - 1].rstrip() if node.lineno <= len(lines) else ""
                violations.append(AntiPatternViolation(
                    rule_name="god_class",
                    severity="critical",
                    line=node.lineno,
                    description=f"God class '{node.name}': {', '.join(reasons)}",
                    snippet=snippet,
                ))
    return violations


def _detect_long_function(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect functions longer than 100 lines."""
    violations: list[AntiPatternViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_lineno = getattr(node, "end_lineno", None)
            if end_lineno is not None:
                func_lines = end_lineno - node.lineno + 1
                if func_lines > 100:
                    snippet = lines[node.lineno - 1].rstrip() if node.lineno <= len(lines) else ""
                    violations.append(AntiPatternViolation(
                        rule_name="long_function",
                        severity="medium",
                        line=node.lineno,
                        description=f"Function '{node.name}' is {func_lines} lines (>100)",
                        snippet=snippet,
                    ))
    return violations


def _detect_unused_imports(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect imports whose names are never referenced in the rest of the source."""
    violations: list[AntiPatternViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()

    # Collect imported names with their line numbers
    imported: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name.split(".")[0]
                imported.append((name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname if alias.asname else alias.name
                imported.append((name, node.lineno))

    # Collect all Name references
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # Walk up to get root name
            val = node.value
            while isinstance(val, ast.Attribute):
                val = val.value
            if isinstance(val, ast.Name):
                used_names.add(val.id)

    # Also check string annotations and comments
    for name, _lineno in imported:
        if name not in used_names:
            # Check if name appears as a string anywhere (e.g. TYPE_CHECKING blocks)
            if re.search(rf'\b{re.escape(name)}\b', source):
                used_names.add(name)

    for name, lineno in imported:
        if name.startswith("_"):
            # Skip private/underscore imports (commonly used for side effects)
            continue
        if name not in used_names:
            snippet = lines[lineno - 1].rstrip() if lineno <= len(lines) else ""
            violations.append(AntiPatternViolation(
                rule_name="unused_import",
                severity="low",
                line=lineno,
                description=f"Import '{name}' appears unused",
                snippet=snippet,
            ))
    return violations


# ---------------------------------------------------------------------------
# Built-in detectors (regex / line-based)
# ---------------------------------------------------------------------------

def _detect_type_ignore_no_reason(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect ``# type: ignore`` comments without a justification bracket."""
    violations: list[AntiPatternViolation] = []
    pattern = re.compile(r"#\s*type:\s*ignore(?!\[)")
    for lineno, line in enumerate(source.splitlines(), start=1):
        if pattern.search(line):
            violations.append(AntiPatternViolation(
                rule_name="type_ignore_no_reason",
                severity="medium",
                line=lineno,
                description="'# type: ignore' without specific error code; use '# type: ignore[code]'",
                snippet=line.rstrip(),
            ))
    return violations


def _detect_deep_nesting(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect lines with >4 levels of indentation (proxy for deep nesting)."""
    violations: list[AntiPatternViolation] = []
    reported_blocks: set[int] = set()  # Only report first line per block
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        # Assume 4-space indentation; >4 levels = indent > 16
        level = indent // 4
        if level > 4:
            block_start = lineno - (lineno % 10)  # Coarse grouping
            if block_start not in reported_blocks:
                reported_blocks.add(block_start)
                violations.append(AntiPatternViolation(
                    rule_name="deep_nesting",
                    severity="medium",
                    line=lineno,
                    description=f"Code nested {level} levels deep (>4); consider extracting to functions",
                    snippet=line.rstrip(),
                ))
    return violations


def _detect_print_statements(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect bare ``print()`` calls in non-debug/non-test code."""
    violations: list[AntiPatternViolation] = []
    # Skip files that look like test or debug scripts
    base = os.path.basename(_path) if _path else ""
    if base.startswith("test_") or base.endswith("_test.py") or "debug" in base.lower():
        return violations
    pattern = re.compile(r"^\s*print\s*\(")
    for lineno, line in enumerate(source.splitlines(), start=1):
        if pattern.match(line):
            violations.append(AntiPatternViolation(
                rule_name="print_statement",
                severity="low",
                line=lineno,
                description="print() in production code; consider using logging module",
                snippet=line.rstrip(),
            ))
    return violations


def _detect_empty_except(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect empty catch blocks (``except ...: pass``)."""
    violations: list[AntiPatternViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # Check if body is just 'pass' or an ellipsis
            if len(node.body) == 1:
                stmt = node.body[0]
                is_pass = isinstance(stmt, ast.Pass)
                is_ellipsis = (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and stmt.value.value is ...
                )
                if is_pass or is_ellipsis:
                    lineno = node.lineno
                    snippet = lines[lineno - 1].rstrip() if lineno <= len(lines) else ""
                    violations.append(AntiPatternViolation(
                        rule_name="empty_except",
                        severity="high",
                        line=lineno,
                        description="Empty except block silently swallows errors; at minimum log the exception",
                        snippet=snippet,
                    ))
    return violations


def _detect_magic_numbers(source: str, _path: str) -> list[AntiPatternViolation]:
    """Detect numeric literals (magic numbers) outside common safe values."""
    violations: list[AntiPatternViolation] = []
    # Safe values: 0, 1, -1, 2, 100, commonly used in range/enumerate/etc.
    safe_values = {0, 1, -1, 2, 0.0, 1.0, 0.5, 100, 100.0}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()

    # Gather all assignment target names to skip constant definitions (UPPER_CASE = 42)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if node.value in safe_values:
                continue
            lineno = node.lineno
            if lineno > len(lines):
                continue
            line_text = lines[lineno - 1]
            # Skip lines that look like named constant definitions
            stripped = line_text.lstrip()
            if re.match(r"^[A-Z_][A-Z0-9_]*\s*[:=]", stripped):
                continue
            # Skip decorator lines, docstrings, comments
            if stripped.startswith("@") or stripped.startswith("#"):
                continue
            # Skip version-like assignments
            if re.match(r"^__\w+__\s*=", stripped):
                continue
            violations.append(AntiPatternViolation(
                rule_name="magic_number",
                severity="low",
                line=lineno,
                description=f"Magic number {node.value!r}; consider using a named constant",
                snippet=line_text.rstrip(),
            ))
    return violations


# ---------------------------------------------------------------------------
# Built-in rule registry
# ---------------------------------------------------------------------------

_BUILTIN_RULES: list[RuleFn] = [
    _detect_bare_except,
    _detect_mutable_defaults,
    _detect_type_ignore_no_reason,
    _detect_god_class,
    _detect_deep_nesting,
    _detect_long_function,
    _detect_unused_imports,
    _detect_print_statements,
    _detect_empty_except,
    _detect_magic_numbers,
]


# ---------------------------------------------------------------------------
# AntiPatternDetector
# ---------------------------------------------------------------------------

class AntiPatternDetector:
    """Configurable anti-pattern detector for Python source files.

    Usage::

        detector = AntiPatternDetector()
        violations = detector.detect("path/to/module.py")
        quality = detector.score("path/to/module.py")
    """

    def __init__(
        self,
        *,
        rules: Optional[list[RuleFn]] = None,
        severity_weights: Optional[dict[str, float]] = None,
        max_violations_weight: float = _MAX_VIOLATIONS_WEIGHT,
    ) -> None:
        self._rules: list[RuleFn] = list(rules) if rules is not None else list(_BUILTIN_RULES)
        self._weights = dict(severity_weights) if severity_weights is not None else dict(_SEVERITY_WEIGHTS)
        self._max_violations = max_violations_weight

    # -- public API --------------------------------------------------------

    def detect(self, file_path: str) -> list[AntiPatternViolation]:
        """Run all registered rules against *file_path* and return violations.

        Raises ``RuntimeError`` if the ``PATTERN_INTELLIGENCE`` feature flag
        is not enabled.
        """
        from claude_experimental.patterns import _require_enabled
        _require_enabled()

        source = self._read_source(file_path)
        violations: list[AntiPatternViolation] = []
        for rule_fn in self._rules:
            violations.extend(rule_fn(source, file_path))
        violations.sort(key=lambda v: v.line)
        return violations

    def score(self, file_path: str) -> float:
        """Return a quality score in ``[0.0, 1.0]`` for *file_path*.

        ``1.0`` means clean (no violations), ``0.0`` means many severe violations.

        Raises ``RuntimeError`` if the ``PATTERN_INTELLIGENCE`` feature flag
        is not enabled.
        """
        from claude_experimental.patterns import _require_enabled
        _require_enabled()

        violations = self._detect_raw(file_path)
        total_weight = sum(
            self._weights.get(v.severity, 0.1) for v in violations
        )
        return max(0.0, 1.0 - total_weight / self._max_violations)

    def add_rule(self, rule_fn: RuleFn) -> None:
        """Register a custom rule function.

        The function signature must be ``(source: str, file_path: str) -> list[AntiPatternViolation]``.
        """
        self._rules.append(rule_fn)

    # -- internal ----------------------------------------------------------

    def _detect_raw(self, file_path: str) -> list[AntiPatternViolation]:
        """Run detection without feature-flag check (for internal use by score)."""
        source = self._read_source(file_path)
        violations: list[AntiPatternViolation] = []
        for rule_fn in self._rules:
            violations.extend(rule_fn(source, file_path))
        violations.sort(key=lambda v: v.line)
        return violations

    @staticmethod
    def _read_source(file_path: str) -> str:
        """Read source code from *file_path*."""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
