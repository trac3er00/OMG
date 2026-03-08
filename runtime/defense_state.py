from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


_DEFENSE_STATE_REL_PATH = Path(".omg") / "state" / "defense_state" / "current.json"
_CONTEXT_PRESSURE_REL_PATH = Path(".omg") / "state" / ".context-pressure.json"
_UNTRUSTED_STATE_REL_PATH = Path(".omg") / "state" / "untrusted-content.json"

_SAFE_STATE: dict[str, Any] = {
    "risk_level": "low",
    "injection_hits": 0,
    "contamination_score": 0.0,
    "overthinking_score": 0.0,
    "actions": [],
    "updated_at": "",
    "reasons": [],
    "thresholds": {
        "critical": {"injection_hits": 3, "contamination_score": 0.7},
        "high": {"injection_hits": 1, "contamination_score": 0.4},
        "medium": {"overthinking_score": 0.5},
    },
    "context_pressure": {
        "tool_count": 0,
        "threshold": 0,
        "is_high": False,
    },
    "trust_posture": "trusted",
}


class DefenseState:
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.state_path = self.project_dir / _DEFENSE_STATE_REL_PATH

    def update(
        self,
        *,
        injection_hits: int = 0,
        contamination_score: float = 0.0,
        overthinking_score: float = 0.0,
    ) -> dict[str, Any]:
        pressure = self._read_json(self.project_dir / _CONTEXT_PRESSURE_REL_PATH)
        pressure_tool_count = self._to_int(pressure.get("tool_count"), default=0)
        pressure_threshold = self._to_int(pressure.get("threshold"), default=0)
        pressure_ratio = 0.0
        if pressure_threshold > 0:
            pressure_ratio = pressure_tool_count / pressure_threshold
        combined_overthinking = max(float(overthinking_score), pressure_ratio)

        trust_posture = self._read_trust_posture()
        level, actions, reasons = self._score(
            injection_hits=max(0, int(injection_hits)),
            contamination_score=self._clamp_score(contamination_score),
            overthinking_score=self._clamp_score(combined_overthinking),
        )
        if pressure_ratio >= 1.0:
            reasons.append("context pressure is above configured threshold")

        state: dict[str, Any] = {
            "risk_level": level,
            "injection_hits": max(0, int(injection_hits)),
            "contamination_score": self._clamp_score(contamination_score),
            "overthinking_score": self._clamp_score(combined_overthinking),
            "actions": actions,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "reasons": reasons,
            "thresholds": {
                "critical": {"injection_hits": 3, "contamination_score": 0.7},
                "high": {"injection_hits": 1, "contamination_score": 0.4},
                "medium": {"overthinking_score": 0.5},
            },
            "context_pressure": {
                "tool_count": pressure_tool_count,
                "threshold": pressure_threshold,
                "is_high": bool(pressure.get("is_high", False)),
                "score": round(self._clamp_score(pressure_ratio), 4),
            },
            "trust_posture": trust_posture,
            "action_recommendations": list(actions),
        }
        self._write_atomic(self.state_path, state)
        return state

    def read(self) -> dict[str, Any]:
        payload = self._read_json(self.state_path)
        if not payload:
            return dict(_SAFE_STATE)
        return {
            "risk_level": str(payload.get("risk_level", "low")),
            "injection_hits": self._to_int(payload.get("injection_hits"), default=0),
            "contamination_score": self._clamp_score(payload.get("contamination_score", 0.0)),
            "overthinking_score": self._clamp_score(payload.get("overthinking_score", 0.0)),
            "actions": self._to_str_list(payload.get("actions")),
            "updated_at": str(payload.get("updated_at", "")),
            "reasons": self._to_str_list(payload.get("reasons")),
            "thresholds": payload.get("thresholds", _SAFE_STATE["thresholds"]),
            "context_pressure": payload.get("context_pressure", _SAFE_STATE["context_pressure"]),
            "trust_posture": str(payload.get("trust_posture", "trusted")),
            "action_recommendations": self._to_str_list(payload.get("action_recommendations")),
        }

    def _read_trust_posture(self) -> str:
        payload = self._read_json(self.project_dir / _UNTRUSTED_STATE_REL_PATH)
        scores = payload.get("trust_scores") if isinstance(payload, dict) else {}
        if not isinstance(scores, dict):
            return "trusted"

        external_score = self._to_float(scores.get("external_content"), default=1.0)
        if external_score <= 0.3:
            return "untrusted"
        if external_score < 1.0:
            return "degraded"
        return "trusted"

    def _score(
        self,
        *,
        injection_hits: int,
        contamination_score: float,
        overthinking_score: float,
    ) -> tuple[str, list[str], list[str]]:
        reasons: list[str] = []
        if injection_hits >= 3 or contamination_score >= 0.7:
            if injection_hits >= 3:
                reasons.append("multiple prompt-injection signals detected")
            if contamination_score >= 0.7:
                reasons.append("contamination score exceeded critical threshold")
            return "critical", ["block", "quarantine"], reasons

        if injection_hits >= 1 or contamination_score >= 0.4:
            if injection_hits >= 1:
                reasons.append("prompt-injection signal detected")
            if contamination_score >= 0.4:
                reasons.append("contamination score exceeded high threshold")
            return "high", ["warn", "flag"], reasons

        if overthinking_score >= 0.5:
            reasons.append("overthinking/cycle pressure exceeded medium threshold")
            return "medium", ["throttle"], reasons

        return "low", [], reasons

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.rename(tmp_path, path)

    def _clamp_score(self, value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed < 0:
            return 0.0
        if parsed > 1:
            return 1.0
        return parsed

    def _to_int(self, value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _to_float(self, value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _to_str_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]
