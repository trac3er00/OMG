"""Session health monitor — combines defense, pressure, verification, and journal signals."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from runtime.runtime_contracts import write_run_state


_SESSION_HEALTH_REL = Path(".omg") / "state" / "session_health"
_DEFENSE_STATE_REL = Path(".omg") / "state" / "defense_state" / "current.json"
_CONTEXT_PRESSURE_REL = Path(".omg") / "state" / ".context-pressure.json"
_JOURNAL_REL = Path(".omg") / "state" / "interaction_journal"

_DEFAULT_THRESHOLDS: dict[str, Any] = {
    "contamination_risk": {"warn": 0.3, "block": 0.7},
    "overthinking_score": {"warn": 0.5, "block": 0.85},
    "context_health": {"warn": 0.4, "critical": 0.2},
}


def compute_session_health(
    project_dir: str,
    *,
    run_id: str = "default",
) -> dict[str, Any]:
    """Aggregate defense, pressure, verification, and journal state into one health artifact."""
    root = Path(project_dir)

    defense = _read_json(root / _DEFENSE_STATE_REL)
    pressure = _read_json(root / _CONTEXT_PRESSURE_REL)
    verification = _read_verification(root, run_id)
    journal_count = _count_journal_entries(root / _JOURNAL_REL)

    contamination_risk = _clamp(_to_float(defense.get("contamination_score"), 0.0))
    injection_hits = _to_int(defense.get("injection_hits"), 0)
    if injection_hits >= 3:
        contamination_risk = max(contamination_risk, 0.9)
    elif injection_hits >= 1:
        contamination_risk = max(contamination_risk, 0.5)

    pressure_ratio = 0.0
    pressure_threshold = _to_int(pressure.get("threshold"), 0)
    pressure_tool_count = _to_int(pressure.get("tool_count"), 0)
    if pressure_threshold > 0:
        pressure_ratio = pressure_tool_count / pressure_threshold

    overthinking_score = _clamp(
        max(
            _to_float(defense.get("overthinking_score"), 0.0),
            pressure_ratio,
        )
    )

    context_health = _compute_context_health(pressure_ratio, journal_count)

    verification_status = str(verification.get("status", "unknown"))

    recommended_action = _recommend_action(
        contamination_risk=contamination_risk,
        overthinking_score=overthinking_score,
        context_health=context_health,
        verification_status=verification_status,
    )

    _ACTION_TO_STATUS = {
        "continue": "ok",
        "warn": "running",
        "reflect": "running",
        "block": "blocked",
    }
    status = _ACTION_TO_STATUS.get(recommended_action, "pending")

    result: dict[str, Any] = {
        "schema": "SessionHealth",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "status": status,
        "contamination_risk": round(contamination_risk, 4),
        "overthinking_score": round(overthinking_score, 4),
        "context_health": round(context_health, 4),
        "verification_status": verification_status,
        "journal_steps": journal_count,
        "recommended_action": recommended_action,
        "thresholds": dict(_DEFAULT_THRESHOLDS),
        "sources": {
            "defense_state": bool(defense),
            "context_pressure": bool(pressure),
            "verification": verification_status != "unknown",
            "journal": journal_count > 0,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    write_run_state(project_dir, "session_health", run_id, result)
    return result


def _recommend_action(
    *,
    contamination_risk: float,
    overthinking_score: float,
    context_health: float,
    verification_status: str,
) -> str:
    thresholds = _DEFAULT_THRESHOLDS

    if contamination_risk >= thresholds["contamination_risk"]["block"]:
        return "block"
    if overthinking_score >= thresholds["overthinking_score"]["block"]:
        return "block"

    if contamination_risk >= thresholds["contamination_risk"]["warn"]:
        return "reflect"
    if overthinking_score >= thresholds["overthinking_score"]["warn"]:
        return "reflect"
    if context_health <= thresholds["context_health"]["critical"]:
        return "reflect"

    if verification_status in ("error", "blocked"):
        return "warn"
    if context_health <= thresholds["context_health"]["warn"]:
        return "warn"

    return "continue"


def _compute_context_health(pressure_ratio: float, journal_count: int) -> float:
    """Return 0..1 where 1 is healthy. Degrades with pressure and journal churn."""
    base = 1.0
    base -= _clamp(pressure_ratio) * 0.5
    if journal_count > 50:
        base -= 0.3
    elif journal_count > 20:
        base -= 0.15
    elif journal_count > 10:
        base -= 0.05
    return max(0.0, min(1.0, base))


def _read_verification(root: Path, run_id: str) -> dict[str, Any]:
    vc_path = root / ".omg" / "state" / "verification_controller" / f"{run_id}.json"
    payload = _read_json(vc_path)
    if payload:
        return payload
    bg_path = root / ".omg" / "state" / "background-verification.json"
    payload = _read_json(bg_path)
    if payload and payload.get("schema") == "BackgroundVerificationState":
        return payload
    return {}


def _count_journal_entries(journal_dir: Path) -> int:
    if not journal_dir.exists():
        return 0
    try:
        return sum(1 for f in journal_dir.iterdir() if f.suffix == ".json" and not f.name.endswith(".tmp"))
    except OSError:
        return 0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.rename(tmp_path, path)


def _clamp(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


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
