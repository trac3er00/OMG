from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ReviewStatus = Literal["pending", "approved", "rejected", "stale"]


@dataclass(slots=True)
class GitHubReviewState:
    head_sha: str
    review_id: int | None
    check_run_id: int | None
    status: ReviewStatus


class GitHubReviewContract:
    def __init__(self) -> None:
        self._state_by_pr: dict[int, GitHubReviewState] = {}

    def get_state(self, pr_number: int) -> GitHubReviewState | None:
        return self._state_by_pr.get(pr_number)

    def should_skip_sha(self, pr_number: int, head_sha: str) -> bool:
        current = self._state_by_pr.get(pr_number)
        if current is None:
            return False
        return current.head_sha == head_sha and current.status in {"pending", "approved", "rejected"}

    def mark_stale_for_new_sha(self, pr_number: int, new_head_sha: str) -> dict[str, object]:
        current = self._state_by_pr.get(pr_number)
        if current is None or current.head_sha == new_head_sha:
            return {"marked": False}

        stale_review_id = current.review_id
        stale_status = current.status
        current.status = "stale"
        return {
            "marked": True,
            "stale_review_id": stale_review_id,
            "stale_status": stale_status,
            "stale_sha": current.head_sha,
        }

    def record_review(
        self,
        *,
        pr_number: int,
        head_sha: str,
        review_id: int | None,
        check_run_id: int | None,
        status: ReviewStatus,
    ) -> GitHubReviewState:
        state = GitHubReviewState(
            head_sha=head_sha,
            review_id=review_id,
            check_run_id=check_run_id,
            status=status,
        )
        self._state_by_pr[pr_number] = state
        return state


__all__ = ["GitHubReviewContract", "GitHubReviewState", "ReviewStatus"]
