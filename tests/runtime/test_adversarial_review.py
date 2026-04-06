from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Protocol, cast


class FindingLike(Protocol):
    severity: str
    category: str
    file: str
    line: int
    description: str
    remediation: str


class ReportLike(Protocol):
    findings: list[FindingLike]
    files_scanned: int
    total_lines: int

    def to_dict(
        self,
    ) -> dict[
        str, str | int | float | bool | None | list[object] | dict[str, object]
    ]: ...


class ReviewerLike(Protocol):
    def scan(self, scope: str | Path = ".") -> ReportLike: ...


class ReviewerFactory(Protocol):
    def __call__(self, severity_floor: str = "medium") -> ReviewerLike: ...


adversarial_review = import_module("runtime.adversarial_review")
AdversarialReview = cast(
    ReviewerFactory, getattr(adversarial_review, "AdversarialReview")
)
CATEGORIES = cast(tuple[str, ...], getattr(adversarial_review, "CATEGORIES"))


def test_detects_sql_injection_f_string(tmp_path: Path):
    code = tmp_path / "test.py"
    _ = code.write_text(
        'result = db.execute(f"SELECT * FROM users WHERE id = {user_id}")'
    )

    review = AdversarialReview(severity_floor="medium")
    report = review.scan(tmp_path)

    injection_findings = [
        finding for finding in report.findings if finding.category == "injection"
    ]
    assert len(injection_findings) > 0, "Should detect SQL injection"
    assert any(
        finding.severity in ("high", "critical") for finding in injection_findings
    )


def test_detects_hardcoded_secret(tmp_path: Path):
    code = tmp_path / "config.py"
    _ = code.write_text('API_KEY = "sk-secret-abc123xyz789"')

    review = AdversarialReview(severity_floor="medium")
    report = review.scan(tmp_path)

    secret_findings = [
        finding for finding in report.findings if finding.category == "hardcoded_secret"
    ]
    assert len(secret_findings) > 0, "Should detect hardcoded secret"


def test_detects_os_system_injection(tmp_path: Path):
    code = tmp_path / "runner.py"
    _ = code.write_text('import os\nos.system(f"rm {filename}")')

    review = AdversarialReview(severity_floor="low")
    report = review.scan(tmp_path)

    assert len(report.findings) > 0
    assert any(finding.category == "injection" for finding in report.findings)


def test_detects_js_eval(tmp_path: Path):
    code = tmp_path / "app.ts"
    _ = code.write_text("const result = eval(userInput);")

    review = AdversarialReview(severity_floor="medium")
    report = review.scan(tmp_path)

    assert len(report.findings) > 0
    assert any(finding.category == "injection" for finding in report.findings)


def test_severity_floor_filters(tmp_path: Path):
    code = tmp_path / "test.py"
    _ = code.write_text(
        'import os\nos.system(f"rm {filename}")\npassword = "hardcoded123"'
    )

    review_high = AdversarialReview(severity_floor="critical")
    report_high = review_high.scan(tmp_path)
    review_low = AdversarialReview(severity_floor="low")
    report_low = review_low.scan(tmp_path)

    assert len(report_high.findings) <= len(report_low.findings)


def test_report_to_dict_has_required_fields(tmp_path: Path):
    code = tmp_path / "test.py"
    _ = code.write_text("pass")

    review = AdversarialReview()
    report = review.scan(tmp_path)
    report_dict = report.to_dict()
    summary = cast(dict[str, object], report_dict["summary"])

    assert "findings" in report_dict
    assert "summary" in report_dict
    assert "files_scanned" in report_dict
    assert "total_lines" in report_dict
    assert "total" in summary


def test_finding_has_all_fields(tmp_path: Path):
    code = tmp_path / "test.py"
    _ = code.write_text("os.system(user_cmd)")

    review = AdversarialReview(severity_floor="low")
    report = review.scan(tmp_path)

    if report.findings:
        finding = report.findings[0]
        assert finding.severity in ("info", "low", "medium", "high", "critical")
        assert finding.category in CATEGORIES
        assert finding.file
        assert finding.line > 0
        assert finding.description
        assert finding.remediation


def test_empty_directory_returns_no_findings(tmp_path: Path):
    review = AdversarialReview()
    report = review.scan(tmp_path)

    assert len(report.findings) == 0
    assert report.files_scanned == 0
