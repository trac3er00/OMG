from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]


SEVERITY_LEVELS = ("info", "low", "medium", "high", "critical")

CATEGORIES = (
    "injection",
    "auth_bypass",
    "data_leak",
    "privilege_escalation",
    "denial_of_service",
    "insecure_dependency",
    "hardcoded_secret",
)


@dataclass
class Finding:
    severity: str
    category: str
    file: str
    line: int
    description: str
    remediation: str
    code_snippet: str = ""


@dataclass
class AdversarialReport:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    total_lines: int = 0

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "findings": [
                {
                    "severity": finding.severity,
                    "category": finding.category,
                    "file": finding.file,
                    "line": finding.line,
                    "description": finding.description,
                    "remediation": finding.remediation,
                    "code_snippet": finding.code_snippet,
                }
                for finding in self.findings
            ],
            "summary": {
                "total": len(self.findings),
                "critical": sum(
                    1 for finding in self.findings if finding.severity == "critical"
                ),
                "high": sum(
                    1 for finding in self.findings if finding.severity == "high"
                ),
                "medium": sum(
                    1 for finding in self.findings if finding.severity == "medium"
                ),
                "low": sum(1 for finding in self.findings if finding.severity == "low"),
            },
            "files_scanned": self.files_scanned,
            "total_lines": self.total_lines,
        }


_PYTHON_PATTERNS: tuple[tuple[re.Pattern[str], str, str, str, str], ...] = (
    (
        re.compile(r'f".*SELECT.*\{', re.IGNORECASE),
        "critical",
        "injection",
        "SQL injection via f-string",
        "Use parameterized queries",
    ),
    (
        re.compile(r'execute\s*\(\s*f"', re.IGNORECASE),
        "critical",
        "injection",
        "SQL injection in execute()",
        "Use parameterized queries",
    ),
    (
        re.compile(r"os\.system\s*\("),
        "high",
        "injection",
        "Shell injection via os.system()",
        "Use subprocess with list args",
    ),
    (
        re.compile(r"subprocess\.(?:call|run|Popen)\s*\([^\[]*shell\s*=\s*True"),
        "high",
        "injection",
        "Shell injection: subprocess with shell=True",
        "Use shell=False with list args",
    ),
    (
        re.compile(r"\beval\s*\("),
        "high",
        "injection",
        "Code injection via eval()",
        "Avoid eval(); use ast.literal_eval for safe parsing",
    ),
    (
        re.compile(
            r"print\s*\(.*(?:password|secret|token|key|credential)", re.IGNORECASE
        ),
        "medium",
        "data_leak",
        "Sensitive data printed to stdout",
        "Remove debug prints with sensitive data",
    ),
    (
        re.compile(r"logging\.\w+\(.*(?:password|secret|token|key)", re.IGNORECASE),
        "medium",
        "data_leak",
        "Sensitive data in log statement",
        "Sanitize log messages",
    ),
    (
        re.compile(
            r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']{6,}["\']',
            re.IGNORECASE,
        ),
        "high",
        "hardcoded_secret",
        "Hardcoded credential detected",
        "Use environment variables or secrets manager",
    ),
    (
        re.compile(r"if\s+.*==\s*True\s*:\s*#.*bypass", re.IGNORECASE),
        "medium",
        "auth_bypass",
        "Possible auth bypass condition",
        "Review this conditional carefully",
    ),
    (
        re.compile(r"while\s+True\s*:"),
        "low",
        "denial_of_service",
        "Unbounded loop detected",
        "Ensure loop has exit condition",
    ),
)

_JS_PATTERNS: tuple[tuple[re.Pattern[str], str, str, str, str], ...] = (
    (
        re.compile(r"eval\s*\("),
        "high",
        "injection",
        "Code injection via eval()",
        "Avoid eval()",
    ),
    (
        re.compile(r"innerHTML\s*="),
        "medium",
        "injection",
        "XSS risk via innerHTML",
        "Use textContent or DOMPurify",
    ),
    (
        re.compile(r"dangerouslySetInnerHTML"),
        "medium",
        "injection",
        "XSS risk via dangerouslySetInnerHTML",
        "Sanitize HTML input",
    ),
    (
        re.compile(
            r'(?:password|secret|apiKey)\s*[:=]\s*["\'][^"\']{6,}["\']', re.IGNORECASE
        ),
        "high",
        "hardcoded_secret",
        "Hardcoded credential in JS/TS",
        "Use environment variables",
    ),
    (
        re.compile(r"child_process\.exec\s*\(.*\$\{"),
        "high",
        "injection",
        "Shell injection via child_process.exec with template literal",
        "Use execFile with args array",
    ),
)


def _severity_index(severity: str) -> int:
    return SEVERITY_LEVELS.index(severity)


def _analyze_lines(
    file_path: Path,
    lines: list[str],
    patterns: tuple[tuple[re.Pattern[str], str, str, str, str], ...],
    severity_floor: str,
) -> list[Finding]:
    minimum_severity = _severity_index(severity_floor)
    findings: list[Finding] = []

    for line_no, line in enumerate(lines, start=1):
        for pattern, severity, category, description, remediation in patterns:
            if _severity_index(severity) < minimum_severity:
                continue
            if pattern.search(line):
                findings.append(
                    Finding(
                        severity=severity,
                        category=category,
                        file=str(file_path),
                        line=line_no,
                        description=description,
                        remediation=remediation,
                        code_snippet=line.strip()[:100],
                    )
                )
    return findings


def _analyze_python_file(file_path: Path, severity_floor: str) -> list[Finding]:
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return _analyze_lines(file_path, lines, _PYTHON_PATTERNS, severity_floor)


def _analyze_js_ts_file(file_path: Path, severity_floor: str) -> list[Finding]:
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return _analyze_lines(file_path, lines, _JS_PATTERNS, severity_floor)


class AdversarialReview:
    def __init__(self, severity_floor: str = "medium"):
        if severity_floor not in SEVERITY_LEVELS:
            raise AssertionError(f"Invalid severity: {severity_floor}")
        self.severity_floor: str = severity_floor

    def scan(self, scope: str | Path = ".") -> AdversarialReport:
        scope_path = Path(scope)
        report = AdversarialReport()

        if scope_path.is_file():
            files = [scope_path]
        elif scope_path.is_dir():
            files = (
                list(scope_path.rglob("*.py"))
                + list(scope_path.rglob("*.ts"))
                + list(scope_path.rglob("*.js"))
            )
            files = [
                file_path
                for file_path in files
                if "node_modules" not in str(file_path)
                and "__pycache__" not in str(file_path)
                and ".git" not in str(file_path)
            ]
        else:
            return report

        report.files_scanned = len(files)

        for file_path in files:
            try:
                report.total_lines += len(
                    file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                )
            except OSError:
                pass

            if file_path.suffix == ".py":
                report.findings.extend(
                    _analyze_python_file(file_path, self.severity_floor)
                )
            elif file_path.suffix in {".js", ".ts", ".jsx", ".tsx"}:
                report.findings.extend(
                    _analyze_js_ts_file(file_path, self.severity_floor)
                )

        return report
