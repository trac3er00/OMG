from __future__ import annotations

from unittest.mock import Mock, patch

from runtime.github_review_bot import GitHubReviewBot, build_check_run_payload
from runtime.verdict_schema import (
    VerdictReceipt,
    action_required_verdict,
    fail_verdict,
    pass_verdict,
)


def _response(status_code: int, payload: dict[str, object]) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = "payload"
    response.headers = {}
    return response


def _called_url(call: object) -> str:
    args = getattr(call, "args", ())
    if isinstance(args, tuple) and args:
        return str(args[0])
    kwargs = getattr(call, "kwargs", {})
    if isinstance(kwargs, dict):
        return str(kwargs.get("url", ""))
    return ""


def test_full_pr_review_flow_with_mocked_github_api():
    event_opened = {
        "action": "opened",
        "repository": {"full_name": "acme/omg"},
        "pull_request": {
            "number": 88,
            "head": {"sha": "sha-1"},
        },
    }
    event_sync = {
        "action": "synchronize",
        "repository": {"full_name": "acme/omg"},
        "pull_request": {
            "number": 88,
            "head": {"sha": "sha-2"},
        },
    }

    pass_evidence = {
        "verdict": "pass",
        "artifacts": ["artifacts/release/.omg/evidence/release-readiness.json"],
        "checks": [{"name": "compat-gate", "status": "ok"}],
        "evidence_gaps": [],
        "inline_comments": [{"path": "runtime/github_review_bot.py", "line": 3, "body": "CI matched expected behavior."}],
    }
    fail_evidence = {
        "verdict": "fail",
        "artifacts": ["artifacts/release/.omg/evidence/release-readiness.json"],
        "checks": [{"name": "compat-gate", "status": "failed", "detail": "required checks missing"}],
        "evidence_gaps": ["required check artifacts missing for latest SHA"],
        "inline_comments": [{"path": "runtime/github_review_bot.py", "line": 4, "body": "Follow-up changes required."}],
    }

    session = Mock()
    session.post.side_effect = [
        _response(200, {"id": 5001}),
        _response(201, {"id": 6001}),
        _response(200, {"id": 5001}),
        _response(200, {"id": 5002}),
        _response(201, {"id": 6002}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "ghs_token"}):
        opened = bot.process_pull_request_event(event_opened, pass_evidence)
        synced = bot.process_pull_request_event(event_sync, fail_evidence)

    assert opened["status"] == "ok"
    assert opened["head_sha"] == "sha-1"
    assert opened["review_status"] == "approved"

    assert synced["status"] == "ok"
    assert synced["head_sha"] == "sha-2"
    assert synced["review_status"] == "rejected"

    called_urls = [_called_url(call) for call in session.post.call_args_list]
    assert called_urls.count("https://api.github.com/repos/acme/omg/pulls/88/reviews") == 2
    assert called_urls.count("https://api.github.com/repos/acme/omg/check-runs") == 2
    assert any(url.endswith("/reviews/5001/dismissals") for url in called_urls)


def test_full_pr_flow_with_external_ci_failure():
    event = {
        "action": "opened",
        "repository": {"full_name": "acme/omg"},
        "pull_request": {
            "number": 99,
            "head": {"sha": "sha-e2e"},
        },
    }
    pass_evidence = {
        "verdict": "pass",
        "artifacts": ["artifacts/release/.omg/evidence/release-readiness.json"],
        "checks": [{"name": "compat-gate", "status": "ok"}],
        "evidence_gaps": [],
        "inline_comments": [],
    }

    session = Mock()
    session.get.return_value = _response(200, {
        "total_count": 2,
        "check_runs": [
            {"name": "build-and-test", "status": "completed", "conclusion": "failure"},
            {"name": "OMG PR Reviewer", "status": "completed", "conclusion": "success"},
        ],
    })
    session.post.side_effect = [
        _response(200, {"id": 10001}),
        _response(201, {"id": 10002}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "ghs_e2e"}):
        result = bot.process_pull_request_event(event, pass_evidence)

    assert result["status"] == "ok"
    assert result["review_status"] == "rejected"
    assert result["head_sha"] == "sha-e2e"

    review_post_call = session.post.call_args_list[0]
    review_body = review_post_call.kwargs.get("json", {}).get("body", "")
    assert "build-and-test" in review_body
    assert "failed" in review_body.lower()


# ---------------------------------------------------------------------------
# build_check_run_payload — standalone App seam tests
# ---------------------------------------------------------------------------


class TestBuildCheckRunPayload:
    """Tests for the standalone-App seam function."""

    def test_fail_verdict_includes_annotations_key(self) -> None:
        verdict = fail_verdict(["no_tests"])
        payload = build_check_run_payload(verdict)
        assert "annotations" in payload["output"]
        assert isinstance(payload["output"]["annotations"], list)

    def test_fail_verdict_with_explicit_annotations(self) -> None:
        verdict = fail_verdict(["no_tests"])
        annotations = [
            {
                "path": "src/main.py",
                "start_line": 10,
                "end_line": 10,
                "annotation_level": "failure",
                "message": "Missing test coverage for new function.",
            }
        ]
        payload = build_check_run_payload(verdict, annotations=annotations)
        assert payload["output"]["annotations"] == annotations
        assert payload["conclusion"] == "failure"

    def test_pass_verdict_maps_to_success(self) -> None:
        verdict = pass_verdict()
        payload = build_check_run_payload(verdict)
        assert payload["conclusion"] == "success"
        assert payload["status"] == "completed"
        assert payload["name"] == "OMG PR Reviewer"

    def test_action_required_verdict_maps_to_action_required(self) -> None:
        verdict = action_required_verdict(["needs manual approval"])
        payload = build_check_run_payload(verdict)
        assert payload["conclusion"] == "action_required"

    def test_pending_verdict_maps_to_neutral(self) -> None:
        verdict: VerdictReceipt = {
            "status": "pending",
            "verdict": "pending",
            "blockers": [],
            "planned_actions": [],
            "executed_actions": [],
            "provenance": None,
            "evidence_paths": {},
            "next_steps": [],
            "executed": False,
            "metadata": {},
        }
        payload = build_check_run_payload(verdict)
        assert payload["conclusion"] == "neutral"

    def test_payload_has_required_fields(self) -> None:
        verdict = pass_verdict()
        payload = build_check_run_payload(verdict)
        assert payload["name"] == "OMG PR Reviewer"
        assert payload["status"] == "completed"
        assert "conclusion" in payload
        output = payload["output"]
        assert "title" in output
        assert "summary" in output
        assert "annotations" in output
        assert "actions" in payload

    def test_blockers_become_annotations_when_no_explicit_annotations(self) -> None:
        verdict = fail_verdict(["no_tests", "lint_errors"])
        payload = build_check_run_payload(verdict)
        annotations = payload["output"]["annotations"]
        assert len(annotations) == 2
        assert all(a["annotation_level"] == "failure" for a in annotations)
        assert annotations[0]["message"] == "no_tests"
        assert annotations[1]["message"] == "lint_errors"

    def test_explicit_annotations_override_blocker_annotations(self) -> None:
        verdict = fail_verdict(["no_tests"])
        explicit = [
            {
                "path": "foo.py",
                "start_line": 5,
                "end_line": 5,
                "annotation_level": "warning",
                "message": "Explicit finding.",
            }
        ]
        payload = build_check_run_payload(verdict, annotations=explicit)
        assert payload["output"]["annotations"] == explicit

    def test_actions_field_is_list(self) -> None:
        verdict = action_required_verdict(["review needed"])
        payload = build_check_run_payload(verdict)
        assert isinstance(payload["actions"], list)


# ---------------------------------------------------------------------------
# Split-lane security model preservation tests
# ---------------------------------------------------------------------------


class TestSplitLaneSecurityModel:
    """Assert the split-lane trusted-posting model is preserved."""

    def test_pr_analyze_job_has_read_only_permissions(self) -> None:
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "omg-compat-gate.yml").read_text()
        pr_analyze = text[text.find("  pr-analyze:"):text.find("  post-review:")]
        assert "permissions:" in pr_analyze
        assert "contents: read" in pr_analyze
        assert "pull-requests: write" not in pr_analyze
        assert "checks: write" not in pr_analyze
        assert "secrets.OMG_APP_ID" not in pr_analyze
        assert "secrets.OMG_APP_PRIVATE_KEY" not in pr_analyze

    def test_post_review_job_uses_trusted_base_sha_checkout(self) -> None:
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "omg-compat-gate.yml").read_text()
        post_review = text[text.find("  post-review:"):text.find("  compat-gate:")]
        assert "ref: ${{ github.event.pull_request.base.sha }}" in post_review
        assert "pull-requests: write" in post_review
        assert "checks: write" in post_review

    def test_post_review_job_has_app_credentials(self) -> None:
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "omg-compat-gate.yml").read_text()
        post_review = text[text.find("  post-review:"):text.find("  compat-gate:")]
        has_app_id = "secrets.OMG_APP_ID" in post_review or "secrets.GITHUB_APP_ID" in post_review
        has_private_key = "secrets.OMG_APP_PRIVATE_KEY" in post_review or "secrets.GITHUB_APP_PRIVATE_KEY" in post_review
        assert has_app_id, "post-review must reference App ID secret"
        assert has_private_key, "post-review must reference App private key secret"
