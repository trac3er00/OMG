from __future__ import annotations


class ElasticPool:
    max_workers: int
    budget_remaining_pct: float
    rate_limited: bool

    def __init__(
        self,
        max_workers: int = 8,
        budget_remaining_pct: float = 100.0,
        rate_limited: bool = False,
    ) -> None:
        self.max_workers = min(max(1, int(max_workers)), 8)
        self.budget_remaining_pct = float(budget_remaining_pct)
        self.rate_limited = bool(rate_limited)

    def compute_agent_count(self, complexity: str) -> int:
        base = {
            "trivial": 1,
            "simple": 2,
            "medium": 3,
            "complex": 6,
            "critical": 8,
        }.get(str(complexity).strip().lower(), 3)

        if self.budget_remaining_pct < 20:
            base = min(base, 2)
        elif self.budget_remaining_pct < 50:
            base = min(base, 4)

        if self.rate_limited:
            base = min(base, 2)

        return min(base, self.max_workers)

    def should_scale_down(self, active_count: int, pending_tasks: int) -> bool:
        return active_count > pending_tasks and pending_tasks > 0

    def max_for_budget(self) -> int:
        if self.budget_remaining_pct < 20:
            return 2
        if self.budget_remaining_pct < 50:
            return 4
        return self.max_workers
