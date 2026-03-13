"""Regex-based import parsers for JavaScript/TypeScript and Go.

These parsers are intentionally lightweight and best-effort.
"""

from pathlib import Path
import re
from typing import NotRequired, TypedDict, cast


class ParseResult(TypedDict):
    imports: list[str]
    accuracy: str
    language: str
    error: NotRequired[str]


def _read_text_file(file_path: str) -> tuple[str | None, str | None]:
    """Read UTF-8 text safely, returning (text, error)."""
    try:
        raw = Path(file_path).read_bytes()
    except OSError as exc:
        return None, f"file-read-error: {exc}"

    if b"\x00" in raw:
        return None, "unparseable-file: binary content detected"

    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"unparseable-file: {exc}"


def _result(imports: list[str], accuracy: str, language: str, error: str | None) -> ParseResult:
    result: ParseResult = {
        "imports": imports,
        "accuracy": accuracy,
        "language": language,
    }
    if error:
        result["error"] = error
    return result


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def parse_js_imports(file_path: str) -> ParseResult:
    """Parse JS/TS import specifiers from a file via regex (~70% accuracy).

    Accuracy: ~70% ("regex-70%").
    Known misses: dynamic imports with variables/template literals,
    complex transpiler syntax, and imports hidden in non-UTF8 files.
    """
    text, error = _read_text_file(file_path)
    if text is None:
        return _result([], "regex-70%", "javascript", error)

    imports: list[str] = []

    static_import_re = re.compile(
        r"^\s*import\s+(?:[\w*$\s{},]+\s+from\s+)?['\"]([^'\"]+)['\"]",
        re.MULTILINE,
    )
    require_re = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
    export_from_re = re.compile(
        r"^\s*export\s+\*\s+from\s+['\"]([^'\"]+)['\"]",
        re.MULTILINE,
    )
    dynamic_import_re = re.compile(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")

    imports.extend(static_import_re.findall(text))
    imports.extend(require_re.findall(text))
    imports.extend(export_from_re.findall(text))
    imports.extend(dynamic_import_re.findall(text))

    return _result(_unique(imports), "regex-70%", "javascript", None)


def parse_go_imports(file_path: str) -> ParseResult:
    """Parse Go import paths from a file via regex (~80% accuracy).

    Accuracy: ~80% ("regex-80%").
    Known misses: imports gated by build tags/conditional file inclusion,
    and non-UTF8 or unparseable files.
    """
    text, error = _read_text_file(file_path)
    if text is None:
        return _result([], "regex-80%", "go", error)

    imports: list[str] = []

    single_or_alias_re = re.compile(
        r'^\s*import\s+(?:[A-Za-z_][\w.]*)?\s*"([^"]+)"',
        re.MULTILINE,
    )
    block_re = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
    block_entry_re = re.compile(r'(?:[A-Za-z_][\w.]*)?\s*"([^"]+)"')

    imports.extend(single_or_alias_re.findall(text))

    for block in cast(list[str], block_re.findall(text)):
        imports.extend(block_entry_re.findall(block))

    return _result(_unique(imports), "regex-80%", "go", None)
