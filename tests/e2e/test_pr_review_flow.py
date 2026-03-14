from __future__ import annotations

from unittest.mock import Mock, patch

from runtime.github_review_bot import GitHubReviewBot


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
