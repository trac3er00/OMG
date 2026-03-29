"""Minimal YAML compatibility layer for OMG.

This keeps standalone/no-vendor flows working when PyYAML is unavailable.
It supports the subset used in OMG configs: mappings, lists, quoted strings,
booleans, numbers, nulls, and simple flow-style collections.
"""
from __future__ import annotations

import io
import json
import logging
from typing import Any


_logger = logging.getLogger(__name__)


def _read_text(stream_or_text: Any) -> str:
    if hasattr(stream_or_text, "read"):
        return str(stream_or_text.read())
    return str(stream_or_text)


def _strip_comments(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    out: list[str] = []
    for char in line:
        if escaped:
            out.append(char)
            escaped = False
            continue
        if char == "\\" and in_double:
            out.append(char)
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            out.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            out.append(char)
            continue
        if char == "#" and not in_single and not in_double:
            break
        out.append(char)
    return "".join(out).rstrip()


def _prepare_lines(text: str) -> list[tuple[int, str]]:
    prepared: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped = _strip_comments(raw_line)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        prepared.append((indent, stripped[indent:]))
    return prepared


def _split_key_value(text: str) -> tuple[str, str] | None:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_double:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == ":" and not in_single and not in_double:
            if index + 1 < len(text) and text[index + 1] not in {" ", "\t"}:
                continue
            return text[:index].strip(), text[index + 1 :].strip()
    return None


def _split_flow_items(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    depth = 0
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and in_double:
            current.append(char)
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            current.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            current.append(char)
            continue
        if char in "[{" and not in_single and not in_double:
            depth += 1
            current.append(char)
            continue
        if char in "]}" and not in_single and not in_double:
            depth -= 1
            current.append(char)
            continue
        if char == "," and not in_single and not in_double and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _parse_scalar(text: str) -> Any:
    if text == "":
        return ""
    if text[0] in {'"', "'"} and text[-1] == text[0]:
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "~"}:
        return None
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item) for item in _split_flow_items(inner)]
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        if not inner:
            return {}
        out: dict[str, Any] = {}
        for item in _split_flow_items(inner):
            pair = _split_key_value(item)
            if pair is None:
                raise ValueError(f"Invalid flow mapping item: {item!r}")
            out[str(_parse_scalar(pair[0]))] = _parse_scalar(pair[1])
        return out
    try:
        if text.startswith("0") and text not in {"0", "0.0"} and not text.startswith("0."):
            raise ValueError
        return int(text)
    except ValueError as exc:
        _logger.debug("Failed integer parse for scalar %r: %s", text, exc, exc_info=True)
    try:
        return float(text)
    except ValueError:
        return text


class _Parser:
    def __init__(self, lines: list[tuple[int, str]]):
        self.lines = lines
        self.index = 0

    def parse(self) -> Any:
        if not self.lines:
            return None
        return self._parse_block(self.lines[0][0])

    def _parse_block(self, indent: int) -> Any:
        if self.index >= len(self.lines):
            return None
        current_indent, content = self.lines[self.index]
        if current_indent < indent:
            return None
        if content.startswith("- "):
            return self._parse_list(indent)
        return self._parse_mapping(indent)

    def _parse_mapping(self, indent: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        while self.index < len(self.lines):
            current_indent, content = self.lines[self.index]
            if current_indent < indent:
                break
            if current_indent != indent or content.startswith("- "):
                break
            pair = _split_key_value(content)
            if pair is None:
                raise ValueError(f"Invalid mapping line: {content!r}")
            raw_key, raw_value = pair
            key = str(_parse_scalar(raw_key))
            self.index += 1
            if raw_value:
                out[key] = _parse_scalar(raw_value)
                continue
            if self.index < len(self.lines) and self.lines[self.index][0] > current_indent:
                out[key] = self._parse_block(self.lines[self.index][0])
            else:
                out[key] = None
        return out

    def _parse_list(self, indent: int) -> list[Any]:
        out: list[Any] = []
        while self.index < len(self.lines):
            current_indent, content = self.lines[self.index]
            if current_indent < indent:
                break
            if current_indent != indent or not content.startswith("- "):
                break
            item_content = content[2:].strip()
            self.index += 1
            if not item_content:
                if self.index < len(self.lines) and self.lines[self.index][0] > current_indent:
                    out.append(self._parse_block(self.lines[self.index][0]))
                else:
                    out.append(None)
                continue

            pair = _split_key_value(item_content)
            if pair is not None and pair[0] and " " not in pair[0]:
                raw_key, raw_value = pair
                item: dict[str, Any] = {str(_parse_scalar(raw_key)): _parse_scalar(raw_value) if raw_value else None}
                if not raw_value and self.index < len(self.lines) and self.lines[self.index][0] > current_indent:
                    item[str(_parse_scalar(raw_key))] = self._parse_block(self.lines[self.index][0])
                if self.index < len(self.lines) and self.lines[self.index][0] > current_indent:
                    extra = self._parse_block(self.lines[self.index][0])
                    if isinstance(extra, dict):
                        item.update(extra)
                out.append(item)
                continue

            out.append(_parse_scalar(item_content))
        return out


def safe_load(stream: Any) -> Any:
    text = _read_text(stream)
    stripped = text.strip()
    if not stripped:
        return None
    if stripped[0] in {"{", "["}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            _logger.debug("Failed JSON parse in safe_load for payload prefix %r: %s", stripped[:40], exc, exc_info=True)
    return _Parser(_prepare_lines(text)).parse()


def _dump_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _dump_lines(value: Any, indent: int) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_dump_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                nested = _dump_lines(item, indent + 2)
                if nested:
                    first = nested[0].strip()
                    lines.append(f"{prefix}- {first}")
                    for line in nested[1:]:
                        lines.append(line)
                else:
                    lines.append(f"{prefix}- {{}}")
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(_dump_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_dump_scalar(item)}")
        return lines
    return [f"{prefix}{_dump_scalar(value)}"]


def safe_dump(
    data: Any,
    stream: io.TextIOBase | None = None,
    default_flow_style: bool | None = None,
    sort_keys: bool = False,
    **_: Any,
) -> str | None:
    _ = default_flow_style
    dump_data = data
    if sort_keys and isinstance(data, dict):
        dump_data = dict(sorted(data.items()))
    text = "\n".join(_dump_lines(dump_data, 0)) + "\n"
    if stream is not None:
        stream.write(text)
        return None
    return text


dump = safe_dump
load = safe_load

__all__ = ["dump", "load", "safe_dump", "safe_load"]
