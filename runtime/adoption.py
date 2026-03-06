"""Native OMG adoption helpers for setup and trust-release surfaces."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CANONICAL_BRAND = "OMG"
CANONICAL_REPO_URL = "https://github.com/trac3er00/OMG"
CANONICAL_PACKAGE_NAME = "@trac3er/oh-my-god"
CANONICAL_PLUGIN_ID = "omg"
CANONICAL_MARKETPLACE_ID = "omg"
CANONICAL_VERSION = "2.0.1"

VALID_ADOPTION_MODES = ("omg-only", "coexist")
VALID_PRESETS = ("safe", "balanced", "interop", "labs")

MANAGED_PRESET_FLAGS = (
    "SETUP",
    "SETUP_WIZARD",
    "MEMORY_AUTOSTART",
    "SESSION_ANALYTICS",
    "CONTEXT_MANAGER",
    "COST_TRACKING",
    "MEMORY_SERVER",
    "GIT_WORKFLOW",
    "TEST_GENERATION",
    "DEP_HEALTH",
    "CODEBASE_VIZ",
)

PRESET_FEATURES: dict[str, dict[str, bool]] = {
    "safe": {flag: False for flag in MANAGED_PRESET_FLAGS},
    "balanced": {
        "SETUP": True,
        "SETUP_WIZARD": True,
        "MEMORY_AUTOSTART": True,
        "SESSION_ANALYTICS": True,
        "CONTEXT_MANAGER": True,
        "COST_TRACKING": True,
        "MEMORY_SERVER": False,
        "GIT_WORKFLOW": False,
        "TEST_GENERATION": False,
        "DEP_HEALTH": False,
        "CODEBASE_VIZ": False,
    },
    "interop": {
        "SETUP": True,
        "SETUP_WIZARD": True,
        "MEMORY_AUTOSTART": True,
        "SESSION_ANALYTICS": True,
        "CONTEXT_MANAGER": True,
        "COST_TRACKING": True,
        "MEMORY_SERVER": True,
        "GIT_WORKFLOW": False,
        "TEST_GENERATION": False,
        "DEP_HEALTH": False,
        "CODEBASE_VIZ": False,
    },
    "labs": {
        "SETUP": True,
        "SETUP_WIZARD": True,
        "MEMORY_AUTOSTART": True,
        "SESSION_ANALYTICS": True,
        "CONTEXT_MANAGER": True,
        "COST_TRACKING": True,
        "MEMORY_SERVER": True,
        "GIT_WORKFLOW": True,
        "TEST_GENERATION": True,
        "DEP_HEALTH": True,
        "CODEBASE_VIZ": True,
    },
}

_SUPERPOWERS_SENTINELS = (
    ("skills", "brainstorming"),
    ("commands", "superpowers.md"),
    ("commands", "superpower.md"),
)


def resolve_preset(preset: str | None) -> str:
    if preset in VALID_PRESETS:
        return preset
    return "safe"


def get_preset_features(preset: str | None) -> dict[str, bool]:
    resolved = resolve_preset(preset)
    return dict(PRESET_FEATURES[resolved])


def _resolve_claude_dir(base_dir: Path) -> Path:
    nested = base_dir / ".claude"
    if nested.exists():
        return nested
    return base_dir


def detect_ecosystems(project_dir: str | Path) -> list[str]:
    root = Path(project_dir)
    claude_dir = _resolve_claude_dir(root)
    detected: list[str] = []

    if (root / ".omc").exists():
        detected.append("omc")
    if (root / ".omx").exists():
        detected.append("omx")

    if any((claude_dir / Path(*parts)).exists() for parts in _SUPERPOWERS_SENTINELS):
        detected.append("superpowers")

    return detected


def recommend_mode(detected_ecosystems: list[str]) -> str:
    if detected_ecosystems:
        return "omg-only"
    return "omg-only"


def _build_actions(mode: str, detected_ecosystems: list[str]) -> list[str]:
    if mode == "coexist":
        actions = [
            "Keep OMG in a non-destructive coexistence mode.",
            "Avoid claiming ownership of third-party command namespaces or HUD surfaces.",
            "Install OMG hooks, MCP, and runtime where they do not overwrite existing ecosystems.",
        ]
        if detected_ecosystems:
            actions.append(
                "Record overlapping ecosystems and route around conflicts instead of disabling them."
            )
        return actions

    actions = [
        "Promote OMG to the primary orchestration, HUD, and MCP layer.",
        "Back up existing OMG-adjacent surfaces before disabling overlaps.",
        "Keep compat available for legacy skill routing without using it as onboarding."
    ]
    if detected_ecosystems:
        actions.append(
            "Adopt portable state where safe and disable overlapping third-party surfaces."
        )
    return actions


def _build_skipped_overlaps(mode: str, detected_ecosystems: list[str]) -> list[str]:
    if not detected_ecosystems:
        return []
    if mode == "coexist":
        return [
            "Third-party slash-command namespaces remain untouched.",
            "Existing HUD and hook ownership is preserved unless explicitly replaced later.",
        ]
    return [
        "Destructive cross-ecosystem migration is skipped unless OMG can back up the prior state first.",
    ]


def _build_follow_up(mode: str, preset: str, detected_ecosystems: list[str]) -> list[str]:
    follow_up = [
        "Run /OMG:setup again whenever providers or auth state change.",
        f"Current preset: {preset}.",
    ]
    if mode == "coexist":
        follow_up.append("Review overlaps before enabling additional OMG labs surfaces.")
    else:
        follow_up.append("Run /OMG:crazy <goal> after setup to use the recommended front door.")
    if detected_ecosystems:
        follow_up.append(
            "Review the adoption report before deleting any previous OMC, OMX, or Superpowers files."
        )
    return follow_up


def build_adoption_report(
    project_dir: str | Path,
    *,
    requested_mode: str | None = None,
    preset: str | None = None,
    adopt: str = "auto",
) -> dict[str, Any]:
    detected_ecosystems = detect_ecosystems(project_dir) if adopt == "auto" else []
    recommended_mode = recommend_mode(detected_ecosystems)
    selected_mode = requested_mode if requested_mode in VALID_ADOPTION_MODES else recommended_mode
    resolved_preset = resolve_preset(preset)

    return {
        "schema": "OmgAdoptionReport",
        "brand": CANONICAL_BRAND,
        "version": CANONICAL_VERSION,
        "repo": CANONICAL_REPO_URL,
        "package": CANONICAL_PACKAGE_NAME,
        "plugin_id": CANONICAL_PLUGIN_ID,
        "marketplace_id": CANONICAL_MARKETPLACE_ID,
        "detected_ecosystems": detected_ecosystems,
        "recommended_mode": recommended_mode,
        "selected_mode": selected_mode,
        "preset": resolved_preset,
        "actions": _build_actions(selected_mode, detected_ecosystems),
        "skipped_overlaps": _build_skipped_overlaps(selected_mode, detected_ecosystems),
        "follow_up": _build_follow_up(selected_mode, resolved_preset, detected_ecosystems),
    }


def write_adoption_report(project_dir: str | Path, report: dict[str, Any]) -> str:
    state_dir = Path(project_dir) / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    report_path = state_dir / "adoption-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(report_path)
