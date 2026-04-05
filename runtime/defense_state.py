from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


_DEFENSE_STATE_REL_PATH = Path(".omg") / "state" / "defense_state" / "current.json"
_CONTEXT_PRESSURE_REL_PATH = Path(".omg") / "state" / ".context-pressure.json"
_UNTRUSTED_STATE_REL_PATH = Path(".omg") / "state" / "untrusted-content.json"
_ACTIVE_RUN_REL_PATH = Path(".omg") / "shadow" / "active-run"
_INTENT_GATE_REL_PATH = Path(".omg") / "state" / "intent_gate"
_SETTINGS_REL_PATH = Path("settings.json")
_POLICY_REL_PATH = Path(".omg") / "policy.yaml"

_DEFAULT_THRESHOLDS: dict[str, dict[str, float | int]] = {
    "critical": {"injection_hits": 3, "contamination_score": 0.7},
    "high": {"injection_hits": 1, "contamination_score": 0.4},
    "medium": {"overthinking_score": 0.5, "premature_fixer_score": 0.5},
}

_SAFE_STATE: dict[str, Any] = {
    "risk_level": "low",
    "injection_hits": 0,
    "contamination_score": 0.0,
    "overthinking_score": 0.0,
    "premature_fixer_score": 0.0,
    "clarification_sensitive": False,
    "actions": [],
    "updated_at": "",
    "reasons": [],
    "thresholds": dict(_DEFAULT_THRESHOLDS),
    "threshold_source": "defaults",
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
        premature_fixer_score: float | None = None,
    ) -> dict[str, Any]:
        thresholds, threshold_source = self._load_thresholds()
        pressure = self._read_json(self.project_dir / _CONTEXT_PRESSURE_REL_PATH)
        pressure_tool_count = self._to_int(pressure.get("tool_count"), default=0)
        pressure_threshold = self._to_int(pressure.get("threshold"), default=0)
        pressure_ratio = 0.0
        if pressure_threshold > 0:
            pressure_ratio = pressure_tool_count / pressure_threshold
        combined_overthinking = max(float(overthinking_score), pressure_ratio)
        normalized_injection_hits = max(0, int(injection_hits))
        normalized_contamination = self._clamp_score(contamination_score)
        normalized_overthinking = self._clamp_score(combined_overthinking)

        clarification = self._read_clarification_signal()
        clarification_sensitive = bool(
            clarification["requires_clarification"]
            or clarification["intent_class"] == "ambiguous_config"
        )
        premature_fixer_score = self._compute_premature_fixer_score(
            clarification_sensitive=clarification_sensitive,
            requires_clarification=bool(clarification["requires_clarification"]),
            confidence=self._to_float(clarification.get("confidence"), default=0.0),
            injection_hits=normalized_injection_hits,
            contamination_score=normalized_contamination,
            overthinking_score=normalized_overthinking,
        )
        scanner_premature_fixer = self._clamp_score(premature_fixer_score)
        premature_fixer_score = max(premature_fixer_score, scanner_premature_fixer)

        trust_posture = self._read_trust_posture()
        level, actions, reasons = self._score(
            injection_hits=normalized_injection_hits,
            contamination_score=normalized_contamination,
            overthinking_score=normalized_overthinking,
            premature_fixer_score=premature_fixer_score,
            thresholds=thresholds,
        )
        if pressure_ratio >= 1.0:
            reasons.append("context pressure is above configured threshold")

        state: dict[str, Any] = {
            "risk_level": level,
            "injection_hits": normalized_injection_hits,
            "contamination_score": normalized_contamination,
            "overthinking_score": normalized_overthinking,
            "premature_fixer_score": round(premature_fixer_score, 4),
            "clarification_sensitive": clarification_sensitive,
            "actions": actions,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "reasons": reasons,
            "thresholds": thresholds,
            "threshold_source": threshold_source,
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
            "contamination_score": self._clamp_score(
                payload.get("contamination_score", 0.0)
            ),
            "overthinking_score": self._clamp_score(
                payload.get("overthinking_score", 0.0)
            ),
            "premature_fixer_score": self._clamp_score(
                payload.get("premature_fixer_score", 0.0)
            ),
            "clarification_sensitive": bool(
                payload.get("clarification_sensitive", False)
            ),
            "actions": self._to_str_list(payload.get("actions")),
            "updated_at": str(payload.get("updated_at", "")),
            "reasons": self._to_str_list(payload.get("reasons")),
            "thresholds": payload.get("thresholds", _SAFE_STATE["thresholds"]),
            "threshold_source": str(payload.get("threshold_source", "defaults")),
            "context_pressure": payload.get(
                "context_pressure", _SAFE_STATE["context_pressure"]
            ),
            "trust_posture": str(payload.get("trust_posture", "trusted")),
            "action_recommendations": self._to_str_list(
                payload.get("action_recommendations")
            ),
        }

    def _read_clarification_signal(self) -> dict[str, Any]:
        active_run_path = self.project_dir / _ACTIVE_RUN_REL_PATH
        if not active_run_path.exists():
            return {
                "requires_clarification": False,
                "intent_class": "",
                "confidence": 0.0,
            }

        try:
            run_id = active_run_path.read_text(encoding="utf-8").strip()
        except OSError:
            run_id = ""
        if not run_id:
            return {
                "requires_clarification": False,
                "intent_class": "",
                "confidence": 0.0,
            }

        intent_gate_path = self.project_dir / _INTENT_GATE_REL_PATH / f"{run_id}.json"
        payload = self._read_json(intent_gate_path)
        confidence = self._clamp_score(
            self._to_float(payload.get("confidence"), default=0.0)
        )
        return {
            "requires_clarification": bool(
                payload.get("requires_clarification") is True
            ),
            "intent_class": str(payload.get("intent_class", "")).strip(),
            "confidence": confidence,
        }

    def _compute_premature_fixer_score(
        self,
        *,
        clarification_sensitive: bool,
        requires_clarification: bool,
        confidence: float,
        injection_hits: int,
        contamination_score: float,
        overthinking_score: float,
    ) -> float:
        if not clarification_sensitive:
            return 0.0

        score = 0.0
        if requires_clarification:
            score += 0.2
        score += min(0.2, self._clamp_score(confidence) * 0.2)
        score += min(0.2, max(0, injection_hits) * 0.1)
        score += min(0.2, self._clamp_score(contamination_score) * 0.25)
        score += min(0.2, self._clamp_score(overthinking_score) * 0.25)
        return self._clamp_score(score)

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

    def _clone_default_thresholds(self) -> dict[str, dict[str, float | int]]:
        return {
            "critical": {
                "injection_hits": int(
                    _DEFAULT_THRESHOLDS["critical"]["injection_hits"]
                ),
                "contamination_score": float(
                    _DEFAULT_THRESHOLDS["critical"]["contamination_score"]
                ),
            },
            "high": {
                "injection_hits": int(_DEFAULT_THRESHOLDS["high"]["injection_hits"]),
                "contamination_score": float(
                    _DEFAULT_THRESHOLDS["high"]["contamination_score"]
                ),
            },
            "medium": {
                "overthinking_score": float(
                    _DEFAULT_THRESHOLDS["medium"]["overthinking_score"]
                ),
                "premature_fixer_score": float(
                    _DEFAULT_THRESHOLDS["medium"]["premature_fixer_score"]
                ),
            },
        }

    def _load_thresholds(self) -> tuple[dict[str, dict[str, float | int]], str]:
        thresholds = self._clone_default_thresholds()
        source = "defaults"

        settings_payload = self._read_json(self.project_dir / _SETTINGS_REL_PATH)
        settings_omg = (
            settings_payload.get("_omg") if isinstance(settings_payload, dict) else None
        )
        if isinstance(settings_omg, dict):
            candidate = settings_omg.get("defense_state")
            if isinstance(candidate, dict):
                if self._apply_threshold_overrides(
                    thresholds, candidate.get("thresholds")
                ):
                    source = "settings._omg.defense_state.thresholds"

        policy_payload = self._read_policy_yaml(self.project_dir / _POLICY_REL_PATH)
        policy_candidate = (
            policy_payload.get("defense_state")
            if isinstance(policy_payload, dict)
            else None
        )
        if isinstance(policy_candidate, dict):
            if self._apply_threshold_overrides(
                thresholds, policy_candidate.get("thresholds")
            ):
                source = ".omg/policy.yaml:defense_state.thresholds"

        return thresholds, source

    def _read_policy_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _apply_threshold_overrides(
        self,
        target: dict[str, dict[str, float | int]],
        candidate: Any,
    ) -> bool:
        if not isinstance(candidate, dict):
            return False
        changed = False

        critical = candidate.get("critical")
        if isinstance(critical, dict):
            if "injection_hits" in critical:
                target["critical"]["injection_hits"] = max(
                    0,
                    self._to_int(
                        critical.get("injection_hits"),
                        default=int(target["critical"]["injection_hits"]),
                    ),
                )
                changed = True
            if "contamination_score" in critical:
                target["critical"]["contamination_score"] = self._clamp_score(
                    critical.get("contamination_score")
                )
                changed = True

        high = candidate.get("high")
        if isinstance(high, dict):
            if "injection_hits" in high:
                target["high"]["injection_hits"] = max(
                    0,
                    self._to_int(
                        high.get("injection_hits"),
                        default=int(target["high"]["injection_hits"]),
                    ),
                )
                changed = True
            if "contamination_score" in high:
                target["high"]["contamination_score"] = self._clamp_score(
                    high.get("contamination_score")
                )
                changed = True

        medium = candidate.get("medium")
        if isinstance(medium, dict):
            if "overthinking_score" in medium:
                target["medium"]["overthinking_score"] = self._clamp_score(
                    medium.get("overthinking_score")
                )
                changed = True
            if "premature_fixer_score" in medium:
                target["medium"]["premature_fixer_score"] = self._clamp_score(
                    medium.get("premature_fixer_score")
                )
                changed = True

        return changed

    def _score(
        self,
        *,
        injection_hits: int,
        contamination_score: float,
        overthinking_score: float,
        premature_fixer_score: float,
        thresholds: dict[str, dict[str, float | int]],
    ) -> tuple[str, list[str], list[str]]:
        reasons: list[str] = []
        critical_hits = self._to_int(
            thresholds["critical"].get("injection_hits"), default=3
        )
        critical_contamination = self._clamp_score(
            thresholds["critical"].get("contamination_score")
        )
        high_hits = self._to_int(thresholds["high"].get("injection_hits"), default=1)
        high_contamination = self._clamp_score(
            thresholds["high"].get("contamination_score")
        )
        medium_overthinking = self._clamp_score(
            thresholds["medium"].get("overthinking_score")
        )
        medium_premature_fixer = self._clamp_score(
            thresholds["medium"].get("premature_fixer_score")
        )

        if (
            injection_hits >= critical_hits
            or contamination_score >= critical_contamination
        ):
            if injection_hits >= critical_hits:
                reasons.append("multiple prompt-injection signals detected")
            if contamination_score >= critical_contamination:
                reasons.append("contamination score exceeded critical threshold")
            return "critical", ["block", "quarantine"], reasons

        if injection_hits >= high_hits or contamination_score >= high_contamination:
            if injection_hits >= high_hits:
                reasons.append("prompt-injection signal detected")
            if contamination_score >= high_contamination:
                reasons.append("contamination score exceeded high threshold")
            return "high", ["warn", "flag"], reasons

        if (
            overthinking_score >= medium_overthinking
            or premature_fixer_score >= medium_premature_fixer
        ):
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
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
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
