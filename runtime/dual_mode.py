"""Dual Mode runtime for OMG — scales from Instant (solo) to Governed (team).

Instant Mode: advisory-only gates, no proof requirements, no claim judge.
             Activated for trivial/simple tasks or via OMG_MODE=instant.
Governed Mode: hard gates, proof required, claim judge, multi-agent orchestration.
              Activated for medium/complex/critical tasks or when team config present.

Used by Tasks 21, 26 for Governed Mode and auto-transition.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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


def evaluate(
    task: dict[str, Any] | None = None,
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
        from runtime.complexity_classifier import classify

        resolved = classify(task).tier
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
