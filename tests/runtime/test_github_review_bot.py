from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock, patch

from runtime.github_review_bot import GitHubReviewBot


def _event(*, action: str, sha: str, pr_number: int = 7, repo: str = "acme/omg") -> dict[str, object]:
    return {
        "action": action,
        "repository": {"full_name": repo},
        "pull_request": {
            "number": pr_number,
            "head": {"sha": sha},
        },
    }


def _evidence(*, verdict: str = "pass", artifacts: list[str] | None = None) -> dict[str, object]:
    return {
        "verdict": verdict,
        "artifacts": artifacts if artifacts is not None else ["artifacts/release/.omg/evidence/release-readiness.json"],
        "checks": [{"name": "release-readiness", "status": "ok"}],
        "evidence_gaps": [],
        "inline_comments": [
            {"path": "runtime/github_review_bot.py", "line": 1, "body": "Looks good."},
        ],
    }


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


def test_sha_scoped_review_post_and_check_run():
    session = Mock()
    session.post.side_effect = [
        _response(200, {"id": 1001}),
        _response(201, {"id": 2002}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "token-1"}):
        result = bot.process_pull_request_event(_event(action="opened", sha="abc123"), _evidence())

    assert result["status"] == "ok"
    assert result["review_id"] == 1001
    assert result["check_run_id"] == 2002
    assert session.post.call_count == 2


def test_idempotency_same_sha_skips_duplicate_posts():
    session = Mock()
    session.post.side_effect = [
        _response(200, {"id": 1001}),
        _response(201, {"id": 2002}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "token-1"}):
        first = bot.process_pull_request_event(_event(action="opened", sha="abc123"), _evidence())
        second = bot.process_pull_request_event(_event(action="reopened", sha="abc123"), _evidence())

    assert first["status"] == "ok"
    assert second["status"] == "skipped"
    assert second["reason"] == "duplicate_sha"
    assert session.post.call_count == 2


def test_synchronize_dismisses_stale_approval_and_posts_new_sha():
    session = Mock()
    session.post.side_effect = [
        _response(200, {"id": 11}),
        _response(201, {"id": 22}),
        _response(200, {"id": 11}),
        _response(200, {"id": 33}),
        _response(201, {"id": 44}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "token-1"}):
        first = bot.process_pull_request_event(_event(action="opened", sha="sha-old"), _evidence(verdict="pass"))
        second = bot.process_pull_request_event(_event(action="synchronize", sha="sha-new"), _evidence(verdict="fail"))

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    urls = [_called_url(call) for call in session.post.call_args_list]
    assert any(url.endswith("/reviews/11/dismissals") for url in urls)
    state = bot.contract.get_state(7)
    assert state is not None
    assert state.head_sha == "sha-new"
    assert state.status == "rejected"


def test_missing_review_artifacts_fails_safely():
    session = Mock()
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "token-1"}):
        result = bot.process_pull_request_event(_event(action="opened", sha="abc123"), _evidence(artifacts=[]))

    assert result["status"] == "error"
    assert result["error_code"] == "GITHUB_REVIEW_ARTIFACTS_MISSING"
    assert session.post.call_count == 0


def test_external_ci_failure_overrides_pass_verdict():
    session = Mock()
    session.get.return_value = _response(200, {
        "total_count": 3,
        "check_runs": [
            {"name": "OMG PR Reviewer", "status": "completed", "conclusion": "success"},
            {"name": "tests / unit", "status": "completed", "conclusion": "failure"},
            {"name": "lint", "status": "completed", "conclusion": "success"},
        ],
    })
    session.post.side_effect = [
        _response(200, {"id": 3001}),
        _response(201, {"id": 4001}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "t"}):
        result = bot.process_pull_request_event(
            _event(action="opened", sha="sha-ext"),
            _evidence(verdict="pass"),
        )

    assert result["status"] == "ok"
    assert result["review_status"] == "rejected"
    session.get.assert_called_once()
    called_url = session.get.call_args[0][0]
    assert "/commits/sha-ext/check-runs" in called_url


def test_checks_api_failure_does_not_block_review():
    session = Mock()
    session.get.side_effect = ConnectionError("timeout")
    session.post.side_effect = [
        _response(200, {"id": 5001}),
        _response(201, {"id": 6001}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "t"}):
        result = bot.process_pull_request_event(
            _event(action="opened", sha="sha-err"),
            _evidence(verdict="pass"),
        )

    assert result["status"] == "ok"
    assert result["review_status"] == "approved"


def test_in_progress_checks_are_not_counted_as_failures():
    session = Mock()
    session.get.return_value = _response(200, {
        "total_count": 2,
        "check_runs": [
            {"name": "deploy", "status": "in_progress", "conclusion": None},
            {"name": "security-scan", "status": "queued", "conclusion": None},
        ],
    })
    session.post.side_effect = [
        _response(200, {"id": 7001}),
        _response(201, {"id": 8001}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "t"}):
        result = bot.process_pull_request_event(
            _event(action="opened", sha="sha-prog"),
            _evidence(verdict="pass"),
        )

    assert result["status"] == "ok"
    assert result["review_status"] == "approved"


def test_compat_gate_own_jobs_are_excluded():
    session = Mock()
    session.get.return_value = _response(200, {
        "total_count": 3,
        "check_runs": [
            {"name": "prepare-compat-gate", "status": "completed", "conclusion": "failure"},
            {"name": "compile-public-compat", "status": "completed", "conclusion": "failure"},
            {"name": "post-review", "status": "completed", "conclusion": "failure"},
        ],
    })
    session.post.side_effect = [
        _response(200, {"id": 9001}),
        _response(201, {"id": 9002}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "t"}):
        result = bot.process_pull_request_event(
            _event(action="opened", sha="sha-own"),
            _evidence(verdict="pass"),
        )

    assert result["status"] == "ok"
    assert result["review_status"] == "approved"


def test_action_required_checks_are_counted_as_failures():
    session = Mock()
    session.get.return_value = _response(200, {
        "total_count": 1,
        "check_runs": [
            {"name": "deploy-prod", "status": "completed", "conclusion": "action_required"},
        ],
    })
    session.post.side_effect = [
        _response(200, {"id": 9101}),
        _response(201, {"id": 9102}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "t"}):
        result = bot.process_pull_request_event(
            _event(action="opened", sha="sha-action"),
            _evidence(verdict="pass"),
        )

    assert result["status"] == "ok"
    assert result["review_status"] == "rejected"


def test_external_ci_failures_follow_pagination():
    first_page = _response(200, {
        "total_count": 101,
        "check_runs": [
            {"name": f"check-{idx}", "status": "completed", "conclusion": "success"}
            for idx in range(100)
        ],
    })
    second_page = _response(200, {
        "total_count": 101,
        "check_runs": [
            {"name": "deploy", "status": "completed", "conclusion": "failure"},
        ],
    })
    session = Mock()
    session.get.side_effect = [first_page, second_page]
    session.post.side_effect = [
        _response(200, {"id": 9201}),
        _response(201, {"id": 9202}),
    ]
    bot = GitHubReviewBot(session=session)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "t"}):
        result = bot.process_pull_request_event(
            _event(action="opened", sha="sha-pages"),
            _evidence(verdict="pass"),
        )

    assert result["status"] == "ok"
    assert result["review_status"] == "rejected"
    assert session.get.call_count == 2
    assert session.get.call_args_list[1].kwargs["params"]["page"] == 2


def test_external_failure_enrichment_does_not_mutate_input_evidence():
    session = Mock()
    session.get.return_value = _response(200, {
        "total_count": 1,
        "check_runs": [
            {"name": "tests / unit", "status": "completed", "conclusion": "failure"},
        ],
    })
    session.post.side_effect = [
        _response(200, {"id": 9301}),
        _response(201, {"id": 9302}),
    ]
    bot = GitHubReviewBot(session=session)
    evidence = _evidence(verdict="pass")
    original = deepcopy(evidence)

    with patch("runtime.github_review_bot.get_github_token", return_value={"status": "ok", "token": "t"}):
        result = bot.process_pull_request_event(
            _event(action="opened", sha="sha-no-mutate"),
            evidence,
        )

    assert result["status"] == "ok"
    assert result["review_status"] == "rejected"
    assert evidence == original
