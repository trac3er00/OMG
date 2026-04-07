from __future__ import annotations

import json
import os
import re
from typing import TypedDict, cast


FP_DATABASE_PATH = os.path.join(".omg", "state", "red-team-fp.json")
REPORT_PATH = os.path.join(".omg", "state", "red-team-report.json")
_SUPPORTED_SUFFIXES = (".py", ".ts", ".js", ".tsx", ".jsx")
_EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".omg"}
_MAX_FILES = 50


class Finding(TypedDict):
    id: str
    file: str
    line: int
    severity: str
    description: str
    snippet: str


class ReviewSession(TypedDict):
    finding_count: int
    findings: list[Finding]
    false_positives_marked: int
    report_path: str
    scanned_files: int


SECURITY_PATTERNS = [
    {
        "id": "sql-injection",
        "pattern": r'execute\s*\(\s*["\'].*%s',
        "severity": "critical",
        "description": "Potential SQL injection via string formatting",
    },
    {
        "id": "shell-injection",
        "pattern": r"os\.system\s*\(|subprocess\.(?:call|run|Popen)\s*\(.*shell\s*=\s*True",
        "severity": "high",
        "description": "Shell injection risk",
    },
    {
        "id": "hardcoded-secret",
        "pattern": r'(?i)(password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}',
        "severity": "high",
        "description": "Hardcoded credential",
    },
    {
        "id": "xss-risk",
        "pattern": r"innerHTML\s*=|document\.write\s*\(",
        "severity": "medium",
        "description": "Potential XSS via innerHTML",
    },
    {
        "id": "eval-usage",
        "pattern": r"\beval\s*\(",
        "severity": "medium",
        "description": "Use of eval() is dangerous",
    },
]


def scan_file(file_path: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
    except OSError:
        return findings

    for pattern_def in SECURITY_PATTERNS:
        matches = list(re.finditer(pattern_def["pattern"], content))
        for match in matches:
            line_num = content[: match.start()].count("\n") + 1
            findings.append(
                {
                    "id": str(pattern_def["id"]),
                    "file": file_path,
                    "line": line_num,
                    "severity": str(pattern_def["severity"]),
                    "description": str(pattern_def["description"]),
                    "snippet": content[
                        max(0, match.start() - 20) : match.end() + 20
                    ].strip(),
                }
            )
    return findings


def load_false_positives() -> set[str]:
    if not os.path.exists(FP_DATABASE_PATH):
        return set()
    try:
        with open(FP_DATABASE_PATH, "r", encoding="utf-8") as handle:
            payload = cast(object, json.load(handle))
    except (OSError, ValueError, TypeError):
        return set()
    values: list[object] = []
    if isinstance(payload, dict):
        payload_map = cast(dict[str, object], payload)
        raw_values = payload_map.get("false_positives", [])
        if isinstance(raw_values, list):
            values = cast(list[object], raw_values)
    return {str(value) for value in values}


def save_false_positive(finding_key: str) -> None:
    false_positives = load_false_positives()
    false_positives.add(finding_key)
    os.makedirs(os.path.dirname(FP_DATABASE_PATH), exist_ok=True)
    with open(FP_DATABASE_PATH, "w", encoding="utf-8") as handle:
        json.dump({"false_positives": sorted(false_positives)}, handle, indent=2)


def _iter_files(scope: str) -> list[str]:
    if os.path.isfile(scope):
        return [os.path.abspath(scope)]

    files_to_scan: list[str] = []
    for root, dirs, files in os.walk(scope):
        dirs[:] = [directory for directory in dirs if directory not in _EXCLUDED_DIRS]
        for filename in files:
            if not filename.endswith(_SUPPORTED_SUFFIXES):
                continue
            files_to_scan.append(os.path.abspath(os.path.join(root, filename)))
            if len(files_to_scan) >= _MAX_FILES:
                return files_to_scan
    return files_to_scan


def interactive_review(scope: str = ".", auto_mode: bool = False) -> ReviewSession:
    del auto_mode

    files_to_scan = _iter_files(scope)
    findings: list[Finding] = []
    for file_path in files_to_scan:
        findings.extend(scan_file(file_path))

    known_false_positives = load_false_positives()
    active_findings = [
        finding
        for finding in findings
        if f"{finding['id']}:{finding['file']}:{finding['line']}"
        not in known_false_positives
    ]

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        json.dump(
            {"findings": active_findings, "scanned_files": len(files_to_scan)},
            handle,
            indent=2,
        )

    return {
        "finding_count": len(active_findings),
        "findings": active_findings,
        "false_positives_marked": 0,
        "report_path": REPORT_PATH,
        "scanned_files": len(files_to_scan),
    }
