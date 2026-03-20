from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runtime.adoption import CANONICAL_VERSION
from runtime.release_artifact_audit import (
    apply_release_artifact_remediation,
    run_release_artifact_audit,
    run_source_tree_audit,
)


def test_run_source_tree_audit_reports_required_sections() -> None:
    report = run_source_tree_audit(ROOT, CANONICAL_VERSION)

    assert report["schema"] == "ArtifactSelfAudit"
    assert report["version_expected"] == CANONICAL_VERSION
    assert "checks" in report
    assert "overall_status" in report
    assert "blockers" in report


def test_run_source_tree_audit_keeps_existing_check_names() -> None:
    report = run_source_tree_audit(ROOT, CANONICAL_VERSION)

    expected = {
        "package_json_version",
        "canonical_version",
        "cli_version_output",
        "changelog_section",
        "install_verification_index",
        "host_list_parity",
        "install_path_hygiene",
    }
    assert expected.issubset(set(report["checks"]))


def test_run_release_artifact_audit_rejects_apply_without_confirmation() -> None:
    report = run_release_artifact_audit(
        ROOT,
        repo="trac3er00/OMG",
        version=CANONICAL_VERSION,
        apply=True,
        confirm="",
        github_token="token",
    )

    assert report["status"] == "error"
    assert report["error_code"] == "RELEASE_AUDIT_CONFIRMATION_REQUIRED"


def test_run_release_artifact_audit_rejects_apply_without_credentials() -> None:
    report = run_release_artifact_audit(
        ROOT,
        repo="trac3er00/OMG",
        version=CANONICAL_VERSION,
        apply=True,
        confirm=CANONICAL_VERSION,
        github_token="",
    )

    assert report["status"] == "error"
    assert report["error_code"] == "GITHUB_TOKEN_MISSING"


class _FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None, *, text: str = "", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object | None]] = []

    def get(self, url: str, *, headers=None, timeout=None):  # noqa: ANN001
        self.calls.append(("GET", url, None))
        if url.endswith(f"/repos/trac3er00/OMG/releases/tags/v{CANONICAL_VERSION}"):
            return _FakeResponse(404, {"message": "Not Found"})
        if url.endswith("/repos/trac3er00/OMG/releases"):
            return _FakeResponse(200, [{"tag_name": "v2.2.9"}])
        if url == "https://github.com/trac3er00/OMG":
            return _FakeResponse(200, text="npx omg env doctor")
        if url == "https://github.com/trac3er00/OMG/releases":
            return _FakeResponse(200, text="Latest v2.2.9")
        if url == f"https://github.com/trac3er00/OMG/releases/tag/v{CANONICAL_VERSION}":
            return _FakeResponse(404, text="Not Found")
        raise AssertionError(f"Unexpected GET {url}")

    def post(self, url: str, *, headers=None, json=None, data=None, timeout=None):  # noqa: ANN001
        body = json if json is not None else data
        self.calls.append(("POST", url, body))
        if url.endswith("/releases"):
            return _FakeResponse(
                201,
                {
                    "id": 42,
                    "tag_name": f"v{CANONICAL_VERSION}",
                    "upload_url": "https://uploads.github.com/repos/trac3er00/OMG/releases/42/assets{?name,label}",
                    "html_url": f"https://github.com/trac3er00/OMG/releases/tag/v{CANONICAL_VERSION}",
                },
            )
        if url.startswith("https://uploads.github.com/"):
            return _FakeResponse(201, {"state": "uploaded"})
        raise AssertionError(f"Unexpected POST {url}")


def test_apply_release_artifact_remediation_creates_release_marks_latest_and_uploads_assets(
    tmp_path: Path,
) -> None:
    notes = tmp_path / "release-body-v2.2.10.md"
    notes.write_text("# Release body\n", encoding="utf-8")
    audit = tmp_path / "release-audit.json"
    audit.write_text('{"status":"ok"}\n', encoding="utf-8")
    session = _FakeSession()

    result = apply_release_artifact_remediation(
        repo="trac3er00/OMG",
        version="2.2.10",
        release_body="# Release body\n",
        asset_paths=[notes, audit],
        release=None,
        github_token="token",
        session=session,
        output_root=tmp_path,
    )

    assert result["status"] == "ok"
    assert result["release_id"] == 42
    assert result["rollback_log"].endswith(".json")
    create_call = session.calls[0]
    assert create_call[0] == "POST"
    assert create_call[1].endswith("/repos/trac3er00/OMG/releases")
    assert create_call[2]["tag_name"] == "v2.2.10"
    assert create_call[2]["make_latest"] == "true"
    upload_calls = [call for call in session.calls if call[1].startswith("https://uploads.github.com/")]
    assert len(upload_calls) == 2


def test_run_release_artifact_audit_flags_remote_release_drift_when_tag_page_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()

    monkeypatch.setattr(
        "runtime.release_artifact_audit.run_source_tree_audit",
        lambda *args, **kwargs: {
            "overall_status": "ok",
            "checks": {"package_json_version": {"status": "ok"}},
            "blockers": [],
        },
    )

    report = run_release_artifact_audit(
        ROOT,
        repo="trac3er00/OMG",
        version=CANONICAL_VERSION,
        session=session,
    )

    assert report["overall_status"] == "fail"
    assert "github_release_missing" in " ".join(report["blockers"])
