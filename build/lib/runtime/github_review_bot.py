from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from runtime.github_integration import get_github_token
from runtime.github_review_contract import GitHubReviewContract, ReviewStatus
from runtime.github_review_formatter import format_review_payload


class GitHubReviewBot:
    def __init__(self, *, session: Any | None = None, api_base: str = "https://api.github.com") -> None:
        self.session = session if session is not None else requests
        self.api_base = api_base.rstrip("/")
        self.contract = GitHubReviewContract()

    def process_pull_request_event(self, event_payload: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        event = self._extract_event(event_payload)
        if event.get("status") != "ok":
            return event

        repo = str(event["repo"])
        pr_number = int(event["pr_number"])
        head_sha = str(event["head_sha"])
        action = str(event["action"])

        if action == "synchronize":
            stale = self.contract.mark_stale_for_new_sha(pr_number, head_sha)
            if stale.get("marked") and stale.get("stale_status") == "approved":
                stale_review_id = stale.get("stale_review_id")
                if isinstance(stale_review_id, int):
                    _ = self._dismiss_review(repo=repo, pr_number=pr_number, review_id=stale_review_id)

        if self.contract.should_skip_sha(pr_number, head_sha):
            state = self.contract.get_state(pr_number)
            return {
                "status": "skipped",
                "reason": "duplicate_sha",
                "repo": repo,
                "pr_number": pr_number,
                "head_sha": head_sha,
                "review_id": state.review_id if state is not None else None,
                "check_run_id": state.check_run_id if state is not None else None,
            }

        token_result = get_github_token(session=self.session)
        if token_result.get("status") != "ok":
            return token_result
        token = str(token_result.get("token", "")).strip()
        if not token:
            return {
                "status": "error",
                "error_code": "GITHUB_TOKEN_EMPTY",
                "message": "GitHub token is empty.",
            }

        formatted = format_review_payload(evidence)
        if formatted.get("status") != "ok":
            return formatted

        review_result = self._post_review(
            repo=repo,
            pr_number=pr_number,
            token=token,
            event=str(formatted["review_event"]),
            body=str(formatted["body"]),
            inline_comments=list(formatted.get("inline_comments", [])),
        )
        if review_result.get("status") != "ok":
            return review_result

        check_result = self._post_check_run(
            repo=repo,
            token=token,
            head_sha=head_sha,
            review_status=str(formatted["review_status"]),
            body=str(formatted["body"]),
        )
        if check_result.get("status") != "ok":
            return check_result

        review_status = self._to_review_status(str(formatted["review_status"]))
        state = self.contract.record_review(
            pr_number=pr_number,
            head_sha=head_sha,
            review_id=self._to_int(review_result.get("review_id")),
            check_run_id=self._to_int(check_result.get("check_run_id")),
            status=review_status,
        )

        return {
            "status": "ok",
            "repo": repo,
            "pr_number": pr_number,
            "head_sha": head_sha,
            "review_id": state.review_id,
            "check_run_id": state.check_run_id,
            "review_status": state.status,
            "inline_comment_count": len(list(formatted.get("inline_comments", []))),
            "dropped_inline_comments": int(formatted.get("dropped_inline_comments", 0) or 0),
        }

    def _extract_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "status": "error",
                "error_code": "GITHUB_EVENT_INVALID",
                "message": "GitHub event payload must be an object.",
            }
        pull_request = payload.get("pull_request")
        repository = payload.get("repository")
        if not isinstance(pull_request, dict) or not isinstance(repository, dict):
            return {
                "status": "error",
                "error_code": "GITHUB_EVENT_INVALID",
                "message": "GitHub event payload must include pull_request and repository.",
            }

        action = str(payload.get("action", "")).strip()
        repo = str(repository.get("full_name", "")).strip()
        pr_number = pull_request.get("number")
        head = pull_request.get("head")
        if not isinstance(head, dict):
            head = {}
        head_sha = str(head.get("sha", "")).strip()

        if not action or not repo or not isinstance(pr_number, int) or not head_sha:
            return {
                "status": "error",
                "error_code": "GITHUB_EVENT_INVALID",
                "message": "GitHub event payload missing action, repository name, PR number, or head sha.",
            }

        return {
            "status": "ok",
            "action": action,
            "repo": repo,
            "pr_number": pr_number,
            "head_sha": head_sha,
        }

    def _post_review(
        self,
        *,
        repo: str,
        pr_number: int,
        token: str,
        event: str,
        body: str,
        inline_comments: list[dict[str, object]],
    ) -> dict[str, object]:
        url = f"{self.api_base}/repos/{repo}/pulls/{pr_number}/reviews"
        headers = self._headers(token)
        payload = {
            "event": event,
            "body": body,
            "comments": inline_comments,
        }
        return self._post(url=url, payload=payload, expected_field="id", error_code="GITHUB_REVIEW_POST_FAILED", headers=headers)

    def _post_check_run(
        self,
        *,
        repo: str,
        token: str,
        head_sha: str,
        review_status: str,
        body: str,
    ) -> dict[str, object]:
        url = f"{self.api_base}/repos/{repo}/check-runs"
        conclusion = {
            "approved": "success",
            "rejected": "failure",
            "pending": "neutral",
        }.get(review_status, "neutral")
        payload = {
            "name": "OMG PR Reviewer",
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion,
            "output": {
                "title": "OMG PR Reviewer verdict",
                "summary": body[:65000],
            },
        }
        headers = self._headers(token)
        return self._post(url=url, payload=payload, expected_field="id", error_code="GITHUB_CHECK_RUN_POST_FAILED", headers=headers)

    def _dismiss_review(self, *, repo: str, pr_number: int, review_id: int) -> dict[str, object]:
        token_result = get_github_token(session=self.session)
        if token_result.get("status") != "ok":
            return token_result
        token = str(token_result.get("token", "")).strip()
        if not token:
            return {
                "status": "error",
                "error_code": "GITHUB_TOKEN_EMPTY",
                "message": "GitHub token is empty.",
            }

        url = f"{self.api_base}/repos/{repo}/pulls/{pr_number}/reviews/{review_id}/dismissals"
        payload = {
            "message": "New commits were pushed; previous approval is stale.",
        }
        headers = self._headers(token)
        return self._post(
            url=url,
            payload=payload,
            expected_field="id",
            error_code="GITHUB_REVIEW_DISMISS_FAILED",
            headers=headers,
        )

    def _post(
        self,
        *,
        url: str,
        payload: Mapping[str, object],
        expected_field: str,
        error_code: str,
        headers: dict[str, str],
    ) -> dict[str, object]:
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=20)
        except Exception as exc:
            return {
                "status": "error",
                "error_code": error_code,
                "message": f"GitHub API call failed: {exc}",
            }

        if int(getattr(response, "status_code", 0)) >= 400:
            return {
                "status": "error",
                "error_code": error_code,
                "http_status": int(getattr(response, "status_code", 0)),
                "message": "GitHub API rejected request.",
                "response_excerpt": str(getattr(response, "text", ""))[:300],
            }
        try:
            payload_json = response.json()
        except Exception:
            payload_json = None
        if not isinstance(payload_json, dict):
            return {
                "status": "error",
                "error_code": error_code,
                "message": "GitHub API response was not valid JSON.",
            }

        value = payload_json.get(expected_field)
        if not isinstance(value, int):
            return {
                "status": "error",
                "error_code": error_code,
                "message": f"GitHub API response missing '{expected_field}'.",
            }
        key = "review_id" if "review" in url and "dismissals" not in url else "check_run_id"
        if "dismissals" in url:
            key = "dismissed_review_id"
        return {
            "status": "ok",
            key: value,
        }

    def _to_int(self, value: object) -> int | None:
        if isinstance(value, int):
            return value
        return None

    def _to_review_status(self, value: str) -> ReviewStatus:
        if value == "approved":
            return "approved"
        if value == "rejected":
            return "rejected"
        if value == "stale":
            return "stale"
        return "pending"

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }


__all__ = ["GitHubReviewBot"]
