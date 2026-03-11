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
    "contamination_risk": {"reflect": 0.05, "block": 0.7},
    "overthinking_score": {"reflect": 0.15, "block": 0.85},
    "premature_fixer_score": {"reflect": 0.5},
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
    premature_fixer_score = _clamp(_to_float(defense.get("premature_fixer_score"), 0.0))
    clarification_sensitive = bool(defense.get("clarification_sensitive") is True)

    context_health = _compute_context_health(pressure_ratio, journal_count)

    verification_status = str(verification.get("status", "unknown"))

    action_recommendations = _recommend_actions(
        contamination_risk=contamination_risk,
        overthinking_score=overthinking_score,
        premature_fixer_score=premature_fixer_score,
        clarification_sensitive=clarification_sensitive,
        context_health=context_health,
        verification_status=verification_status,
    )
    recommended_action = action_recommendations[0] if action_recommendations else "continue"
    reflect_triggers = {
        "contamination": contamination_risk > _DEFAULT_THRESHOLDS["contamination_risk"]["reflect"],
        "overthinking": overthinking_score > _DEFAULT_THRESHOLDS["overthinking_score"]["reflect"],
        "premature_fixer": premature_fixer_score > _DEFAULT_THRESHOLDS["premature_fixer_score"]["reflect"],
    }

    _ACTION_TO_STATUS = {
        "continue": "ok",
        "warn": "running",
        "reflect": "running",
        "block": "blocked",
    }
    status = _ACTION_TO_STATUS.get(recommended_action, "running")

    result: dict[str, Any] = {
        "schema": "SessionHealth",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "status": status,
        "contamination_risk": round(contamination_risk, 4),
        "overthinking_score": round(overthinking_score, 4),
        "premature_fixer_score": round(premature_fixer_score, 4),
        "clarification_sensitive": clarification_sensitive,
        "context_health": round(context_health, 4),
        "verification_status": verification_status,
        "journal_steps": journal_count,
        "recommended_action": recommended_action,
        "action_recommendations": action_recommendations,
        "defense_pause_required": bool(reflect_triggers["contamination"] or reflect_triggers["overthinking"]),
        "reflect_triggers": reflect_triggers,
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


def _recommend_actions(
    *,
    contamination_risk: float,
    overthinking_score: float,
    premature_fixer_score: float,
    clarification_sensitive: bool,
    context_health: float,
    verification_status: str,
) -> list[str]:
    thresholds = _DEFAULT_THRESHOLDS
    actions: list[str] = []

    if contamination_risk >= thresholds["contamination_risk"]["block"]:
        actions.append("block")
    if overthinking_score >= thresholds["overthinking_score"]["block"]:
        actions.append("block")

    if actions:
        return ["block"]

    if clarification_sensitive:
        if contamination_risk > thresholds["contamination_risk"]["reflect"]:
            actions.append("reflect")
        if overthinking_score > thresholds["overthinking_score"]["reflect"]:
            actions.append("reflect")
        if premature_fixer_score > thresholds["premature_fixer_score"]["reflect"]:
            actions.append("reflect")

    if context_health <= thresholds["context_health"]["critical"]:
        actions.append("reflect")

    if verification_status in ("error", "blocked"):
        actions.append("warn")
    if context_health <= thresholds["context_health"]["warn"]:
        actions.append("warn")

    if actions:
        deduped: list[str] = []
        for action in actions:
            if action not in deduped:
                deduped.append(action)
        return deduped

    return ["continue"]


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


_BOUNDED_ACTIONS = frozenset({"continue", "warn", "reflect", "pause", "require-review"})

_HEALTH_TO_AUTO_ACTION: dict[str, str] = {
    "block": "pause",
    "reflect": "reflect",
    "warn": "warn",
    "continue": "continue",
}


def evaluate_auto_actions(
    health: dict[str, Any],
    *,
    profile_risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recommended = str(health.get("recommended_action", "continue"))
    action = _HEALTH_TO_AUTO_ACTION.get(recommended, "warn")

    risk = profile_risk if isinstance(profile_risk, dict) else {}
    risk_requires_review = bool(risk.get("requires_review"))
    has_destructive = bool(risk.get("destructive_entries"))

    review_route: str | None = None

    if action == "pause" and (risk_requires_review or has_destructive):
        action = "require-review"
        review_route = "/OMG:profile-review"
    elif action in ("warn", "reflect") and risk_requires_review:
        action = "require-review"
        review_route = "/OMG:profile-review"
    elif risk_requires_review:
        review_route = "/OMG:profile-review"

    reason = _build_action_reason(health, action, risk)

    return {
        "action": action,
        "reason": reason,
        "review_route": review_route,
        "bounded": True,
        "health_status": str(health.get("status", "unknown")),
        "recommended_action": recommended,
    }


def persist_auto_action_evidence(
    project_dir: str,
    action_result: dict[str, Any],
    *,
    run_id: str = "default",
) -> str:
    root = Path(project_dir)
    actions_dir = root / ".omg" / "state" / "session_health" / "actions"
    actions_dir.mkdir(parents=True, exist_ok=True)
    path = actions_dir / f"{run_id}.json"

    evidence: dict[str, Any] = {
        "schema": "SessionHealthAutoAction",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "action": str(action_result.get("action", "continue")),
        "reason": str(action_result.get("reason", "")),
        "review_route": action_result.get("review_route"),
        "bounded": True,
        "health_status": str(action_result.get("health_status", "unknown")),
        "recommended_action": str(action_result.get("recommended_action", "continue")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _write_atomic(path, evidence)
    return str(path)


def _build_action_reason(
    health: dict[str, Any],
    action: str,
    risk: dict[str, Any],
) -> str:
    parts: list[str] = []

    contamination = _to_float(health.get("contamination_risk"), 0.0)
    overthinking = _to_float(health.get("overthinking_score"), 0.0)
    context_health = _to_float(health.get("context_health"), 1.0)

    if action == "pause":
        if contamination >= _DEFAULT_THRESHOLDS["contamination_risk"]["block"]:
            parts.append(f"contamination_risk={contamination:.2f} >= block threshold")
        if overthinking >= _DEFAULT_THRESHOLDS["overthinking_score"]["block"]:
            parts.append(f"overthinking_score={overthinking:.2f} >= block threshold")
    elif action == "reflect":
        if contamination > _DEFAULT_THRESHOLDS["contamination_risk"]["reflect"]:
            parts.append(f"contamination_risk={contamination:.2f} > reflect threshold")
        if overthinking > _DEFAULT_THRESHOLDS["overthinking_score"]["reflect"]:
            parts.append(f"overthinking_score={overthinking:.2f} > reflect threshold")
    elif action == "warn":
        verification = str(health.get("verification_status", ""))
        if verification in ("error", "blocked"):
            parts.append(f"verification_status={verification}")
        if context_health <= _DEFAULT_THRESHOLDS["context_health"]["warn"]:
            parts.append(f"context_health={context_health:.2f} <= warn threshold")

    if action == "require-review":
        parts.append("profile_risk requires /OMG:profile-review")

    if risk.get("destructive_entries"):
        parts.append(f"{len(risk['destructive_entries'])} destructive preference(s) detected")

    if not parts:
        parts.append("session healthy")

    return "; ".join(parts)
