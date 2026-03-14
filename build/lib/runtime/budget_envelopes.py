"""Multi-dimensional budget envelopes — CPU, memory, wall time, tokens, and network.

Tracks per-run and per-worker resource usage against configurable limits.
Persists envelope state to `.omg/state/budget-envelopes/<run_id>.json`.
Feeds into session health, worker watchdogs, and governed tool decisions.

Governance actions:
  - warn:    log only, no execution impact
  - reflect: pause and report to supervisor
  - block:   terminate / reject further work
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════


@dataclass
class BudgetEnvelope:
    """Declared resource limits for a run or worker."""

    run_id: str
    cpu_seconds_limit: float = 0.0
    memory_mb_limit: float = 0.0
    wall_time_seconds_limit: float = 0.0
    token_limit: int = 0
    network_bytes_limit: int = 0


@dataclass
class BudgetEnvelopeState:
    """Current resource usage tracking for a run or worker."""

    run_id: str
    cpu_seconds_used: float = 0.0
    memory_mb_peak: float = 0.0
    wall_time_seconds_elapsed: float = 0.0
    tokens_used: int = 0
    network_bytes_used: int = 0
    started_at: str = ""
    updated_at: str = ""


@dataclass
class EnvelopeCheckResult:
    """Result of checking a run against its envelope limits."""

    status: str  # "ok", "warn", "breach"
    breached_dimensions: list[str] = field(default_factory=list)
    governance_action: str = "warn"  # "warn", "reflect", "block"
    reason: str = ""


# ═══════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════

_GOVERNANCE_ACTIONS = frozenset({"warn", "reflect", "block"})

# Warn at 80%, block at 100% by default
_DEFAULT_WARN_RATIO = 0.80
_DEFAULT_BLOCK_RATIO = 1.00

_ENVELOPE_STATE_REL = Path(".omg") / "state" / "budget-envelopes"


# ═══════════════════════════════════════════════════════════
# Manager
# ═══════════════════════════════════════════════════════════


class BudgetEnvelopeManager:
    """Create, track, and enforce multi-dimensional budget envelopes.

    Envelopes are persisted as JSON to `.omg/state/budget-envelopes/<run_id>.json`.
    """

    def __init__(self, project_dir: str | None = None):
        if project_dir:
            self.project_dir = Path(project_dir)
        else:
            self.project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    # --- Paths ---

    def _envelope_dir(self) -> Path:
        return self.project_dir / _ENVELOPE_STATE_REL

    def _envelope_path(self, run_id: str) -> Path:
        return self._envelope_dir() / f"{run_id}.json"

    # --- CRUD ---

    def create_envelope(
        self,
        run_id: str,
        *,
        cpu_seconds_limit: float = 0.0,
        memory_mb_limit: float = 0.0,
        wall_time_seconds_limit: float = 0.0,
        token_limit: int = 0,
        network_bytes_limit: int = 0,
    ) -> dict[str, Any]:
        """Create and persist a new budget envelope for *run_id*.

        Returns the full persisted state dict.
        """
        now = _now_iso()
        envelope = BudgetEnvelope(
            run_id=run_id,
            cpu_seconds_limit=cpu_seconds_limit,
            memory_mb_limit=memory_mb_limit,
            wall_time_seconds_limit=wall_time_seconds_limit,
            token_limit=token_limit,
            network_bytes_limit=network_bytes_limit,
        )
        state = BudgetEnvelopeState(
            run_id=run_id,
            started_at=now,
            updated_at=now,
        )
        payload: dict[str, Any] = {
            "schema": "BudgetEnvelopeState",
            "schema_version": "1.0.0",
            "envelope": asdict(envelope),
            "usage": asdict(state),
            "checks": [],
        }
        _write_atomic_json(self._envelope_path(run_id), payload)
        return payload

    def record_usage(
        self,
        run_id: str,
        *,
        cpu_seconds: float = 0.0,
        memory_mb: float = 0.0,
        wall_time_seconds: float = 0.0,
        tokens: int = 0,
        network_bytes: int = 0,
    ) -> dict[str, Any]:
        """Increment usage counters for *run_id*.

        Memory is tracked as peak (max), all others are additive.
        Returns the updated state dict.
        """
        payload = self._read_state(run_id)
        if not payload:
            # Auto-create a zero-limit envelope (uncapped) so usage is still tracked
            payload = self.create_envelope(run_id)

        usage = payload.get("usage", {})
        usage["cpu_seconds_used"] = _to_float(usage.get("cpu_seconds_used"), 0.0) + cpu_seconds
        usage["memory_mb_peak"] = max(
            _to_float(usage.get("memory_mb_peak"), 0.0),
            memory_mb,
        )
        usage["wall_time_seconds_elapsed"] = (
            _to_float(usage.get("wall_time_seconds_elapsed"), 0.0) + wall_time_seconds
        )
        usage["tokens_used"] = _to_int(usage.get("tokens_used"), 0) + tokens
        usage["network_bytes_used"] = _to_int(usage.get("network_bytes_used"), 0) + network_bytes
        usage["updated_at"] = _now_iso()
        payload["usage"] = usage

        _write_atomic_json(self._envelope_path(run_id), payload)
        return payload

    def check_envelope(self, run_id: str) -> EnvelopeCheckResult:
        """Compare current usage against envelope limits.

        Returns an ``EnvelopeCheckResult`` with status, breached dimensions, and
        the appropriate governance action.

        Governance escalation logic:
          - No limit set (0) → dimension is uncapped, never breaches.
          - Usage >= 100% of limit → status=breach, action=block.
          - Usage >= 80% of limit → status=warn, action=warn (first time) or reflect (repeated).
          - Otherwise → status=ok, action=warn (no-op).
        """
        payload = self._read_state(run_id)
        if not payload:
            return EnvelopeCheckResult(status="ok", reason="no envelope found")

        envelope = payload.get("envelope", {})
        usage = payload.get("usage", {})
        checks_history: list[dict[str, Any]] = payload.get("checks", [])

        breached: list[str] = []
        warned: list[str] = []

        _DIMS: list[tuple[str, str, str]] = [
            ("cpu_seconds_limit", "cpu_seconds_used", "cpu"),
            ("memory_mb_limit", "memory_mb_peak", "memory"),
            ("wall_time_seconds_limit", "wall_time_seconds_elapsed", "wall_time"),
            ("token_limit", "tokens_used", "tokens"),
            ("network_bytes_limit", "network_bytes_used", "network"),
        ]

        for limit_key, used_key, dim_name in _DIMS:
            limit_val = _to_float(envelope.get(limit_key), 0.0)
            if limit_val <= 0:
                continue  # uncapped
            used_val = _to_float(usage.get(used_key), 0.0)
            ratio = used_val / limit_val

            if ratio >= _DEFAULT_BLOCK_RATIO:
                breached.append(dim_name)
            elif ratio >= _DEFAULT_WARN_RATIO:
                warned.append(dim_name)

        # Determine governance action
        if breached:
            status = "breach"
            governance_action = "block"
            reason = f"envelope breached on: {', '.join(breached)}"
        elif warned:
            # Escalate to reflect if we warned before on the same dimensions
            prior_warned = set()
            for chk in checks_history:
                if chk.get("status") == "warn":
                    prior_warned.update(chk.get("breached_dimensions", []))
            repeat_warns = set(warned) & prior_warned
            if repeat_warns:
                status = "warn"
                governance_action = "reflect"
                reason = f"repeated warning on: {', '.join(sorted(repeat_warns))}"
            else:
                status = "warn"
                governance_action = "warn"
                reason = f"approaching limits on: {', '.join(warned)}"
        else:
            status = "ok"
            governance_action = "warn"  # no-op sentinel
            reason = "all dimensions within limits"

        result = EnvelopeCheckResult(
            status=status,
            breached_dimensions=breached or warned,
            governance_action=governance_action,
            reason=reason,
        )

        # Persist check result in history
        check_record = {
            "checked_at": _now_iso(),
            "status": result.status,
            "breached_dimensions": list(result.breached_dimensions),
            "governance_action": result.governance_action,
            "reason": result.reason,
        }
        checks_history.append(check_record)
        payload["checks"] = checks_history
        _write_atomic_json(self._envelope_path(run_id), payload)

        return result

    def get_envelope_state(self, run_id: str) -> dict[str, Any] | None:
        """Read current envelope state from disk.

        Returns the full state dict or None if no envelope exists.
        """
        payload = self._read_state(run_id)
        return payload if payload else None

    def get_envelope_pressure(self, run_id: str) -> dict[str, float]:
        """Return per-dimension usage ratios (0.0–1.0+) for health integration.

        Returns empty dict if no envelope exists.
        """
        payload = self._read_state(run_id)
        if not payload:
            return {}

        envelope = payload.get("envelope", {})
        usage = payload.get("usage", {})
        pressure: dict[str, float] = {}

        _DIMS: list[tuple[str, str, str]] = [
            ("cpu_seconds_limit", "cpu_seconds_used", "cpu"),
            ("memory_mb_limit", "memory_mb_peak", "memory"),
            ("wall_time_seconds_limit", "wall_time_seconds_elapsed", "wall_time"),
            ("token_limit", "tokens_used", "tokens"),
            ("network_bytes_limit", "network_bytes_used", "network"),
        ]

        for limit_key, used_key, dim_name in _DIMS:
            limit_val = _to_float(envelope.get(limit_key), 0.0)
            if limit_val <= 0:
                continue
            used_val = _to_float(usage.get(used_key), 0.0)
            pressure[dim_name] = round(used_val / limit_val, 4)

        return pressure

    # --- Internal ---

    def _read_state(self, run_id: str) -> dict[str, Any]:
        return _read_json(self._envelope_path(run_id))


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_budget_envelope_manager(project_dir: str | None = None) -> BudgetEnvelopeManager:
    """Factory for BudgetEnvelopeManager instances."""
    return BudgetEnvelopeManager(project_dir)
