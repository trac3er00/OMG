"""Generate lightweight test skeletons from source files.

Python symbol extraction uses ``ast`` for precise parsing of top-level public
functions, classes, and class methods.

JavaScript/TypeScript symbol extraction uses regular expressions for exported
declarations (``export function``, ``export const``, ``export default
function``, ``export class``). This regex approach is intentionally lightweight
and expected to be about 70-80% accurate for common code styles.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re


_RE_JS_EXPORT_FUNCTION = re.compile(r"(?:^|\s)export\s+function\s+([A-Za-z_$][\w$]*)\s*\(")
_RE_JS_EXPORT_CONST = re.compile(r"(?:^|\s)export\s+const\s+([A-Za-z_$][\w$]*)\s*=")
_RE_JS_EXPORT_DEFAULT_FUNCTION = re.compile(
    r"(?:^|\s)export\s+default\s+function(?:\s+([A-Za-z_$][\w$]*))?\s*\("
)
_RE_JS_EXPORT_CLASS = re.compile(r"(?:^|\s)export\s+class\s+([A-Za-z_$][\w$]*)\b")


def generate_test_skeleton(source_file: str, framework_info: dict[str, object]) -> str:
    path = Path(source_file)
    if not path.exists():
        return ""

    source_text = path.read_text(encoding="utf-8")
    if not source_text.strip():
        return ""

    framework = str(framework_info.get("framework", "")).lower()

    functions: list[str]
    classes: dict[str, list[str]]
    if path.suffix == ".py":
        functions, classes = _extract_python_symbols(source_text)
    else:
        functions, classes = _extract_js_ts_symbols(source_text)

    if framework == "pytest":
        return _render_pytest(functions, classes)
    if framework in {"jest", "vitest"}:
        return _render_jest_vitest(functions, classes)
    if framework == "go":
        return _render_go(functions, classes)
    return _render_generic(functions, classes)


def _extract_python_symbols(source_text: str) -> tuple[list[str], dict[str, list[str]]]:
    functions: list[str] = []
    classes: dict[str, list[str]] = {}

    tree = ast.parse(source_text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            public_methods: list[str] = []
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and not member.name.startswith("_"):
                    public_methods.append(member.name)
            classes[node.name] = public_methods

    return functions, classes


def _extract_js_ts_symbols(source_text: str) -> tuple[list[str], dict[str, list[str]]]:
    functions: list[str] = []
    classes: dict[str, list[str]] = {}

    functions.extend(_RE_JS_EXPORT_FUNCTION.findall(source_text))
    functions.extend(_RE_JS_EXPORT_CONST.findall(source_text))

    for match in _RE_JS_EXPORT_DEFAULT_FUNCTION.findall(source_text):
        functions.append(match or "defaultExport")

    for class_name in _RE_JS_EXPORT_CLASS.findall(source_text):
        classes[class_name] = []

    return _dedupe(functions), classes


def _render_pytest(functions: list[str], classes: dict[str, list[str]]) -> str:
    lines: list[str] = []

    for func_name in functions:
        lines.extend(
            [
                f"def test_{func_name}_happy_path():",
                "    # TODO: implement test",
                "    # happy path",
                "    assert True",
                "",
                f"def test_{func_name}_error_case():",
                "    # TODO: implement test",
                "    # error case",
                "    assert True",
                "",
            ]
        )

    for class_name, methods in classes.items():
        lines.append(f"class Test{class_name}:")
        if not methods:
            lines.extend(["    # TODO: implement test", "    pass", ""])
            continue

        for method_name in methods:
            lines.extend(
                [
                    f"    def test_{method_name}_happy_path(self):",
                    "        # TODO: implement test",
                    "        # happy path",
                    "        assert True",
                    "",
                    f"    def test_{method_name}_error_case(self):",
                    "        # TODO: implement test",
                    "        # error case",
                    "        assert True",
                    "",
                ]
            )

    return "\n".join(lines).rstrip()


def _render_jest_vitest(functions: list[str], classes: dict[str, list[str]]) -> str:
    names = functions + list(classes.keys())
    blocks: list[str] = []

    for name in names:
        blocks.extend(
            [
                f"describe('{name}', () => {{",
                "  it('should happy path', () => {",
                "    // TODO: implement test",
                "    // happy path",
                "    expect(value).toBe(expected);",
                "  });",
                "",
                "  it('should error case', () => {",
                "    // TODO: implement test",
                "    // error case",
                "    expect(value).toBe(expected);",
                "  });",
                "});",
                "",
            ]
        )

    return "\n".join(blocks).rstrip()


def _render_go(functions: list[str], classes: dict[str, list[str]]) -> str:
    names = functions + list(classes.keys())
    if not names:
        return ""

    lines = [
        "package main",
        "",
        'import "testing"',
        "",
    ]

    for name in names:
        test_name = _to_pascal_case(name)
        lines.extend(
            [
                f"func Test{test_name}(t *testing.T) {{",
                "    // TODO: implement test",
                "    // happy path",
                "    // error case",
                "}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def _render_generic(functions: list[str], classes: dict[str, list[str]]) -> str:
    names = functions + list(classes.keys())
    if not names:
        return ""

    lines = []
    for name in names:
        lines.extend(
            [
                f"# Test skeleton for {name}",
                "# TODO: implement test",
                "# happy path",
                "# error case",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _to_pascal_case(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(part[:1].upper() + part[1:] for part in parts if part) or "Generated"
