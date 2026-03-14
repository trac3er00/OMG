# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false
from __future__ import annotations

import json
import sys
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

sys.path.insert(0, str(ROOT / "scripts"))
import github_review_helpers as helpers  # noqa: E402


def _read_workflow_text(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def _section(text: str, start_marker: str, end_marker: str | None = None) -> str:
    start = text.find(start_marker)
    assert start >= 0, f"Missing marker: {start_marker}"
    if end_marker is None:
        return text[start:]
    end = text.find(end_marker, start)
    assert end >= 0, f"Missing end marker: {end_marker}"
    return text[start:end]


def _contains_secret_ref(text: str, key: str) -> bool:
    return f"secrets.{key}" in text


def test_all_target_workflows_define_concurrency() -> None:
    for workflow_name in ("omg-compat-gate.yml", "omg-release-readiness.yml", "publish-npm.yml"):
        text = _read_workflow_text(workflow_name)
        assert re.search(r"^concurrency:\n  group: \$\{\{ github\.workflow \}\}-\$\{\{ github\.ref \}\}\n  cancel-in-progress: true", text, flags=re.MULTILINE)


def test_compat_workflow_has_split_pr_analyze_and_trusted_post_review_jobs() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    assert "  pr-analyze:\n" in text
    assert "  post-review:\n" in text

    pr_analyze = _section(text, "  pr-analyze:\n", "  post-review:\n")
    post_review = _section(text, "  post-review:\n", "  compat-gate:\n")

    assert "permissions:\n      contents: read" in pr_analyze
    assert not _contains_secret_ref(pr_analyze, "GITHUB_APP_ID")
    assert not _contains_secret_ref(pr_analyze, "GITHUB_APP_PRIVATE_KEY")
    assert not _contains_secret_ref(pr_analyze, "GITHUB_INSTALLATION_ID")

    assert "pull-requests: write" in post_review
    assert "checks: write" in post_review
    assert _contains_secret_ref(post_review, "GITHUB_APP_ID")
    assert _contains_secret_ref(post_review, "GITHUB_APP_PRIVATE_KEY")
    assert _contains_secret_ref(post_review, "GITHUB_INSTALLATION_ID")


def test_trusted_post_review_lane_never_checks_out_pr_head() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    post_review = _section(text, "  post-review:\n", "  compat-gate:\n")
    assert "uses: actions/checkout@v4" in post_review
    assert "ref: ${{ github.event.pull_request.base.sha }}" in post_review
    assert "head.sha" not in post_review


def test_fast_pr_blockers_reuse_uploaded_artifacts() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    pr_analyze = _section(text, "  pr-analyze:\n", "  post-review:\n")
    assert "uses: actions/download-artifact@v4" in pr_analyze
    assert "pattern: compat-*" in pr_analyze
    assert "scripts/github_review_helpers.py build-pr-handoff" in pr_analyze
    assert "scripts/github_review_helpers.py assert-pass" in pr_analyze
    assert "scripts/omg.py release readiness" not in pr_analyze


def test_release_readiness_workflow_uploads_reviewer_bot_handoff_artifact() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    assert "scripts/github_review_helpers.py build-release-handoff" in release_job
    assert "reviewer-bot-release-input" in release_job


def test_github_review_helpers_build_pr_handoff_and_assert_pass(tmp_path: Path) -> None:
    event = {
        "action": "opened",
        "repository": {"full_name": "acme/omg"},
        "pull_request": {"number": 7, "head": {"sha": "abc123"}},
    }
    artifacts = tmp_path / "artifacts"
    (artifacts / "public/.omg/evidence").mkdir(parents=True)
    (artifacts / "public/dist/public").mkdir(parents=True)

    (artifacts / "omg-compat-gap.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "omg-compat-contracts.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "public/.omg/evidence/doctor.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "public/dist/public/manifest.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "public/.omg/evidence/host-parity-run-1.json").write_text(
        json.dumps({"parity_results": {"passed": True}}),
        encoding="utf-8",
    )

    payload = helpers.build_pr_handoff(event, artifacts)
    assert payload["verdict"] == "pass"
    assert any(check["name"] == "identity" and check["status"] == "ok" for check in payload["checks"])
    assert any(check["name"] == "parity" and check["status"] == "ok" for check in payload["checks"])

    helpers.assert_pass(payload)


def test_github_review_helpers_assert_pass_fails_when_required_artifacts_missing(tmp_path: Path) -> None:
    event = {
        "action": "opened",
        "repository": {"full_name": "acme/omg"},
        "pull_request": {"number": 9, "head": {"sha": "def456"}},
    }
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True)

    payload = helpers.build_pr_handoff(event, artifacts)
    assert payload["verdict"] == "fail"
    with pytest.raises(SystemExit):
        helpers.assert_pass(payload)
