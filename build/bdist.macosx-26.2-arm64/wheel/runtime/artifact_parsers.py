from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


def parse_junit(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {"valid": False, "summary": {}, "error": "file_not_found"}

    try:
        root = ElementTree.parse(file_path).getroot()
    except (ElementTree.ParseError, OSError, ValueError) as exc:
        return {"valid": False, "summary": {}, "error": f"junit_parse_error:{exc}"}

    root_name = _local_name(root.tag)
    if root_name not in {"testsuite", "testsuites"}:
        return {
            "valid": False,
            "summary": {"root": root_name},
            "error": "junit_invalid_root",
        }

    tests_value = root.attrib.get("tests", "")
    return {
        "valid": True,
        "summary": {"root": root_name, "tests": str(tests_value).strip()},
        "error": None,
    }


def parse_sarif(path: str) -> dict[str, Any]:
    payload, error = _load_json(Path(path))
    if error:
        return {"valid": False, "summary": {}, "error": error}

    runs = payload.get("runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return {"valid": False, "summary": {}, "error": "sarif_missing_runs"}

    return {
        "valid": True,
        "summary": {"runs": len(runs), "version": str(payload.get("version", "")).strip()},
        "error": None,
    }


def parse_coverage(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {"valid": False, "summary": {}, "error": "file_not_found"}

    xml_result = _parse_coverage_xml(file_path)
    if xml_result["valid"]:
        return xml_result

    json_result = _parse_coverage_json(file_path)
    if json_result["valid"]:
        return json_result

    return {
        "valid": False,
        "summary": {},
        "error": xml_result.get("error") or json_result.get("error") or "coverage_missing_keys",
    }


def parse_browser_trace(path: str) -> dict[str, Any]:
    payload, error = _load_json(Path(path))
    if error:
        return {"valid": False, "summary": {}, "error": error}

    if not isinstance(payload, dict):
        return {"valid": False, "summary": {}, "error": "browser_trace_invalid_payload"}

    has_trace = "trace" in payload
    has_events = isinstance(payload.get("events"), list)
    if not (has_trace or has_events):
        return {
            "valid": False,
            "summary": {},
            "error": "browser_trace_missing_trace_or_events",
        }

    return {
        "valid": True,
        "summary": {"has_trace": has_trace, "event_count": len(payload.get("events", [])) if has_events else 0},
        "error": None,
    }


def parse_diff_hunk(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {"valid": False, "summary": {}, "error": "file_not_found"}

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"valid": False, "summary": {}, "error": f"diff_read_error:{exc}"}

    if "@@" not in content:
        return {"valid": False, "summary": {}, "error": "diff_missing_hunk_marker"}

    hunk_count = content.count("@@") // 2 if content.count("@@") >= 2 else 1
    return {"valid": True, "summary": {"hunk_count": hunk_count}, "error": None}


def _parse_coverage_xml(file_path: Path) -> dict[str, Any]:
    try:
        root = ElementTree.parse(file_path).getroot()
    except (ElementTree.ParseError, OSError, ValueError):
        return {"valid": False, "summary": {}, "error": "coverage_xml_parse_error"}

    if "line-rate" in root.attrib:
        return {
            "valid": True,
            "summary": {"line-rate": str(root.attrib.get("line-rate", "")).strip()},
            "error": None,
        }

    return {"valid": False, "summary": {}, "error": "coverage_missing_line_rate"}


def _parse_coverage_json(file_path: Path) -> dict[str, Any]:
    payload, error = _load_json(file_path)
    if error:
        return {"valid": False, "summary": {}, "error": error}

    if not isinstance(payload, dict):
        return {"valid": False, "summary": {}, "error": "coverage_json_invalid_payload"}

    if "coverage" not in payload:
        return {"valid": False, "summary": {}, "error": "coverage_missing_coverage_key"}

    return {
        "valid": True,
        "summary": {"coverage": payload.get("coverage")},
        "error": None,
    }


def _load_json(file_path: Path) -> tuple[Any, str | None]:
    if not file_path.exists():
        return {}, "file_not_found"

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"json_parse_error:{exc}"

    return payload, None


def _local_name(tag: str) -> str:
    if "}" not in tag:
        return tag
    return tag.rsplit("}", 1)[-1]
