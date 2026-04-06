"""Dual Mode runtime for OMG — scales from Instant (solo) to Governed (team).

Instant Mode: advisory-only gates, no proof requirements, no claim judge.
             Activated for trivial/simple tasks or via OMG_MODE=instant.
Governed Mode: hard gates, proof required, claim judge, multi-agent orchestration.
              Activated for medium/complex/critical tasks or when team config present.

Used by Tasks 21, 26 for Governed Mode and auto-transition.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any


MODE_INSTANT = "instant"
MODE_GOVERNED = "governed"


@dataclass
class ModeResult:
    mode: str
    complexity: str
    reason: str
    governance_active: bool


@dataclass
class TransitionEvent:
    from_mode: str
    to_mode: str
    trigger: str
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            import time

            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _has_team_config(project_dir: str = ".") -> bool:
    policy_path = Path(project_dir) / ".omg" / "policy.yaml"
    if not policy_path.exists():
        return False
    try:
        import yaml

        data = yaml.safe_load(policy_path.read_text())
        if isinstance(data, dict) and data.get("team"):
            return True
    except Exception:
        pass
    return False


def _classify_task(task: Mapping[str, object]) -> str:
    module = import_module("runtime.complexity_classifier")
    classify = getattr(module, "classify", None)
    if not callable(classify):
        return "medium"
    result = classify(task)
    tier = getattr(result, "tier", None)
    return tier if isinstance(tier, str) else "medium"


def _coerce_file_count(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def evaluate(
    task: Mapping[str, object] | None = None,
    complexity: str | None = None,
    project_dir: str = ".",
) -> ModeResult:
    """Evaluate which mode to use for the given task.

    Args:
        task: Task dict passed to complexity_classifier.classify()
        complexity: Pre-computed complexity tier (skips classifier if provided)
        project_dir: Project root directory (for team config detection)

    Returns:
        ModeResult with mode and reasoning
    """
    resolved: str
    if complexity is not None:
        resolved = complexity
    elif task is not None:
        resolved = _classify_task(task)
    else:
        resolved = "medium"

    if _has_team_config(project_dir):
        return ModeResult(
            mode=MODE_GOVERNED,
            complexity=resolved,
            reason="team_config_present",
            governance_active=True,
        )

    env_mode = os.environ.get("OMG_MODE", "").strip().lower()

    if env_mode == MODE_INSTANT:
        return ModeResult(
            mode=MODE_INSTANT,
            complexity=resolved,
            reason="env_override_instant",
            governance_active=False,
        )

    if resolved in ("trivial", "simple"):
        return ModeResult(
            mode=MODE_INSTANT,
            complexity=resolved,
            reason=f"low_complexity_{resolved}",
            governance_active=False,
        )
    else:
        return ModeResult(
            mode=MODE_GOVERNED,
            complexity=resolved,
            reason=f"high_complexity_{resolved}",
            governance_active=True,
        )


def get_mode_prefix(result: ModeResult) -> str:
    """Get the visual indicator prefix for governed mode messages.

    Returns '[GOVERNED] ' for governed mode, empty string for instant mode.
    """
    if result.mode == MODE_GOVERNED:
        return "[GOVERNED] "
    return ""


def format_mode_message(result: ModeResult, message: str) -> str:
    """Format a message with mode prefix for user-facing output.

    Example: format_mode_message(result, "Running test suite")
    → "[GOVERNED] Running test suite" (in governed mode)
    → "Running test suite" (in instant mode)
    """
    return f"{get_mode_prefix(result)}{message}"


def get_governance_requirements(
    result: ModeResult, project_dir: str = "."
) -> dict[str, Any]:
    """Get governance requirements based on current mode and team policy.

    Returns dict with keys:
      - proof_required: bool
      - claim_judge_active: bool
      - gate_mode: 'hard' | 'advisory'
      - note: str
    """
    if result.mode == MODE_INSTANT:
        return {
            "proof_required": False,
            "claim_judge_active": False,
            "gate_mode": "advisory",
            "note": "Instant mode: governance advisory-only",
        }

    requirements: dict[str, Any] = {
        "proof_required": True,
        "claim_judge_active": True,
        "gate_mode": "hard",
        "note": "Governed mode: full governance active",
    }

    policy_path = Path(project_dir) / ".omg" / "policy.yaml"
    if policy_path.exists():
        try:
            import yaml

            data = yaml.safe_load(policy_path.read_text())
            if isinstance(data, dict):
                team = data.get("team", {})
                if isinstance(team, dict) and team.get("overrides"):
                    requirements["note"] += " (team overrides applied)"
        except Exception:
            pass

    return requirements


class DualModeSession:
    def __init__(self, initial_complexity: str = "trivial", project_dir: str = "."):
        initial = evaluate(complexity=initial_complexity, project_dir=project_dir)
        self._mode: str = initial.mode
        self._project_dir: str = project_dir
        self._transitions: list[TransitionEvent] = []
        self._task_history: list[str] = []

    @property
    def mode(self) -> str:
        return self._mode

    def update(
        self, task: Mapping[str, object] | None = None, complexity: str | None = None
    ) -> ModeResult:
        if complexity is None and task is not None:
            complexity = _classify_task(task)
        elif complexity is None:
            complexity = "medium"

        resolved_complexity = complexity
        self._task_history.append(resolved_complexity)

        env_mode = os.environ.get("OMG_MODE", "").strip().lower()
        if env_mode == MODE_INSTANT:
            if self._mode != MODE_INSTANT:
                self._record_transition(self._mode, MODE_INSTANT, "user_override")
                self._mode = MODE_INSTANT
            return ModeResult(
                mode=MODE_INSTANT,
                complexity=resolved_complexity,
                reason="env_override_instant",
                governance_active=False,
            )

        new_result = evaluate(
            complexity=resolved_complexity, project_dir=self._project_dir
        )
        trigger: str | None = None

        if self._mode == MODE_INSTANT and new_result.mode == MODE_GOVERNED:
            trigger = "complexity_escalation"

        files = _coerce_file_count(task.get("files", 0)) if task else 0
        if task and files >= 8 and self._mode == MODE_INSTANT:
            trigger = "multi_file_change"
            new_result = ModeResult(
                mode=MODE_GOVERNED,
                complexity=resolved_complexity,
                reason="multi_file_escalation",
                governance_active=True,
            )

        risk_indicators = task.get("risk_indicators", []) if task else []
        if (
            isinstance(risk_indicators, list)
            and any(
                isinstance(risk, str) and risk in {"security", "auth", "data_loss"}
                for risk in risk_indicators
            )
            and self._mode == MODE_INSTANT
        ):
            trigger = "security_sensitive_code"
            new_result = ModeResult(
                mode=MODE_GOVERNED,
                complexity=resolved_complexity,
                reason="security_sensitive_escalation",
                governance_active=True,
            )

        if trigger and self._mode != new_result.mode:
            self._record_transition(self._mode, new_result.mode, trigger)
            self._mode = new_result.mode

        return new_result

    def _record_transition(self, from_mode: str, to_mode: str, trigger: str) -> None:
        self._transitions.append(
            TransitionEvent(from_mode=from_mode, to_mode=to_mode, trigger=trigger)
        )

    def get_transitions(self) -> list[TransitionEvent]:
        return list(self._transitions)

    def get_transition_message(self) -> str | None:
        if not self._transitions:
            return None
        last = self._transitions[-1]
        return (
            f"[GOVERNED] Switching to Governed Mode: {last.trigger.replace('_', ' ')}"
        )
