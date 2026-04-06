"""Cost and latency governor for OMG sessions.

Tracks: tokens used, estimated cost, wall time, API call count.
Enforces: per-session limits (tokens, cost, time).
Alerts: at 80% thresholds.
Integrates with model_router.py budget tracking.
"""
from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field
from typing import cast


_DEFAULT_TOKEN_LIMIT = 500_000  # 500K tokens
_DEFAULT_COST_LIMIT_USD = 5.0  # $5
_DEFAULT_TIME_LIMIT_SECS = 3600  # 1 hour
_WARN_THRESHOLD = 0.80


@dataclass
class UsageSnapshot:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    wall_time_secs: float = 0.0
    api_calls: int = 0
    model_id: str = ""

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass
class GovernorLimits:
    max_tokens: int = _DEFAULT_TOKEN_LIMIT
    max_cost_usd: float = _DEFAULT_COST_LIMIT_USD
    max_time_secs: float = _DEFAULT_TIME_LIMIT_SECS


@dataclass
class GovernorStatus:
    ok: bool
    tokens_pct: float
    cost_pct: float
    time_pct: float
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CostGovernor:
    """Session-level cost and latency governor."""

    limits: GovernorLimits
    project_dir: str
    _total: UsageSnapshot
    _session_start: float
    _snapshots: list[UsageSnapshot]

    def __init__(self, limits: GovernorLimits | None = None, project_dir: str = "."):
        self.limits = limits or GovernorLimits()
        self.project_dir = project_dir
        self._total = UsageSnapshot()
        self._session_start = time.time()
        self._snapshots = []

    def record(
        self,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float | None = None,
        model_id: str = "",
    ) -> GovernorStatus:
        """Record an API call and check limits.

        Returns GovernorStatus — check .ok before proceeding.
        """
        elapsed = time.time() - self._session_start
        snapshot = UsageSnapshot(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd if cost_usd is not None else (tokens_in + tokens_out) * 0.000003,
            wall_time_secs=elapsed,
            api_calls=1,
            model_id=model_id,
        )
        self._total.tokens_in += snapshot.tokens_in
        self._total.tokens_out += snapshot.tokens_out
        self._total.cost_usd += snapshot.cost_usd
        self._total.wall_time_secs = elapsed
        self._total.api_calls += 1
        self._snapshots.append(snapshot)
        return self.check_status()

    def check_status(self) -> GovernorStatus:
        """Check current usage against limits. Emit warnings if needed."""
        elapsed = time.time() - self._session_start
        self._total.wall_time_secs = elapsed

        tokens_pct = self._total.tokens_total / self.limits.max_tokens if self.limits.max_tokens else 0.0
        cost_pct = self._total.cost_usd / self.limits.max_cost_usd if self.limits.max_cost_usd else 0.0
        time_pct = elapsed / self.limits.max_time_secs if self.limits.max_time_secs else 0.0

        violations: list[str] = []
        warns: list[str] = []

        if tokens_pct >= 1.0:
            violations.append(f"Token limit exceeded: {self._total.tokens_total:,}/{self.limits.max_tokens:,}")
        if cost_pct >= 1.0:
            violations.append(f"Cost limit exceeded: ${self._total.cost_usd:.4f}/${self.limits.max_cost_usd:.2f}")
        if time_pct >= 1.0:
            violations.append(f"Time limit exceeded: {elapsed:.0f}s/{self.limits.max_time_secs:.0f}s")

        if _WARN_THRESHOLD <= tokens_pct < 1.0:
            msg = f"Token usage at {tokens_pct * 100:.0f}% of limit"
            warns.append(msg)
            warnings.warn(msg, ResourceWarning, stacklevel=2)
        if _WARN_THRESHOLD <= cost_pct < 1.0:
            msg = f"Cost at {cost_pct * 100:.0f}% of limit (${self._total.cost_usd:.4f})"
            warns.append(msg)
            warnings.warn(msg, ResourceWarning, stacklevel=2)
        if _WARN_THRESHOLD <= time_pct < 1.0:
            msg = f"Wall time at {time_pct * 100:.0f}% of limit ({elapsed:.0f}s)"
            warns.append(msg)
            warnings.warn(msg, ResourceWarning, stacklevel=2)

        return GovernorStatus(
            ok=len(violations) == 0,
            tokens_pct=round(tokens_pct, 4),
            cost_pct=round(cost_pct, 4),
            time_pct=round(time_pct, 4),
            violations=violations,
            warnings=warns,
        )

    def get_summary(self) -> dict[str, object]:
        """Get full usage summary."""
        elapsed = time.time() - self._session_start
        self._total.wall_time_secs = elapsed
        return cast(
            dict[str, object],
            {
                "tokens_in": self._total.tokens_in,
                "tokens_out": self._total.tokens_out,
                "tokens_total": self._total.tokens_total,
                "cost_usd": round(self._total.cost_usd, 6),
                "wall_time_secs": round(elapsed, 1),
                "api_calls": self._total.api_calls,
                "limits": {
                    "max_tokens": self.limits.max_tokens,
                    "max_cost_usd": self.limits.max_cost_usd,
                    "max_time_secs": self.limits.max_time_secs,
                },
            },
        )
