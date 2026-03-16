"""Native OMG adoption helpers for setup and trust-release surfaces."""
from __future__ import annotations

import json
import importlib
import shutil
from pathlib import Path
from typing import Callable, cast

from runtime.canonical_taxonomy import CANONICAL_PRESETS, RELEASE_CHANNELS


CANONICAL_BRAND = "OMG"
CANONICAL_REPO_URL = "https://github.com/trac3er00/OMG"
CANONICAL_PACKAGE_NAME = "@trac3er/oh-my-god"
CANONICAL_PLUGIN_ID = "omg"
CANONICAL_MARKETPLACE_ID = "omg"
CANONICAL_VERSION = "2.2.4"

VALID_ADOPTION_MODES = ("omg-only", "coexist")
CANONICAL_MODE_NAMES = ("chill", "focused", "exploratory")

PRESET_ORDER: tuple[str, ...] = CANONICAL_PRESETS
VALID_PRESETS = CANONICAL_PRESETS
VALID_RELEASE_CHANNELS = RELEASE_CHANNELS
PRESET_LEVEL: dict[str, int] = {p: i for i, p in enumerate(PRESET_ORDER)}

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
    "DATA_ENFORCEMENT",
    "WEB_ENFORCEMENT",
    "TERMS_ENFORCEMENT",
    "COUNCIL_ROUTING",
    "FORGE_ALL_DOMAINS",
    "NOTEBOOKLM",
)

_BUFFET_ONLY_FLAGS = (
    "DATA_ENFORCEMENT",
    "WEB_ENFORCEMENT",
    "TERMS_ENFORCEMENT",
    "COUNCIL_ROUTING",
    "FORGE_ALL_DOMAINS",
    "NOTEBOOKLM",
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
        **{f: False for f in _BUFFET_ONLY_FLAGS},
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
        **{f: False for f in _BUFFET_ONLY_FLAGS},
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
        **{f: False for f in _BUFFET_ONLY_FLAGS},
    },
    "buffet": {flag: True for flag in MANAGED_PRESET_FLAGS},
    "production": {flag: True for flag in MANAGED_PRESET_FLAGS},
}

_SUPERPOWERS_SENTINELS = (
    ("skills", "brainstorming"),
    ("commands", "superpowers.md"),
    ("commands", "superpower.md"),
)


def resolve_preset(preset: str) -> str:
    if preset == "plugins-first":
        return "interop"
    if preset in VALID_PRESETS:
        return preset
    raise ValueError(f"Unknown preset: {preset}")


def get_preset_features(preset: str | None) -> dict[str, bool]:
    resolved = resolve_preset(preset or "safe")
    return dict(PRESET_FEATURES[resolved])


def get_mode_profile(mode: str) -> dict[str, object]:
    runtime_profile = importlib.import_module("runtime.runtime_profile")
    loader = cast(Callable[[str], dict[str, object]], getattr(runtime_profile, "load_canonical_mode_profile"))
    return loader(mode)


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


_CLI_SENTINELS = ("codex", "gemini", "kimi")


def recommend_mode(detected_ecosystems: list[str]) -> str:
    if detected_ecosystems:
        return "coexist"
    for cli in _CLI_SENTINELS:
        if shutil.which(cli):
            return "coexist"
    return "omg-only"


def detect_missing_settings(project_dir: str | Path) -> list[dict[str, str]]:
    root = Path(project_dir)
    missing: list[dict[str, str]] = []

    if not (root / "settings.json").exists():
        missing.append({
            "surface": "settings.json",
            "message": "No settings.json found — host config not initialized",
        })
    if not (root / ".mcp.json").exists():
        missing.append({
            "surface": ".mcp.json",
            "message": "No .mcp.json found — MCP servers not configured",
        })
    if not (root / ".omg" / "state").exists():
        missing.append({
            "surface": ".omg/state",
            "message": "No .omg/state/ directory found — OMG state not initialized",
        })

    return missing


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
) -> dict[str, object]:
    detected_ecosystems = detect_ecosystems(project_dir) if adopt == "auto" else []
    recommended_mode = recommend_mode(detected_ecosystems)
    selected_mode = requested_mode if requested_mode in VALID_ADOPTION_MODES else recommended_mode
    resolved_preset = resolve_preset(preset or "safe")
    missing_settings = detect_missing_settings(project_dir)

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
        "missing_settings": missing_settings,
        "actions": _build_actions(selected_mode, detected_ecosystems),
        "skipped_overlaps": _build_skipped_overlaps(selected_mode, detected_ecosystems),
        "follow_up": _build_follow_up(selected_mode, resolved_preset, detected_ecosystems),
    }


def write_adoption_report(project_dir: str | Path, report: dict[str, object]) -> str:
    state_dir = Path(project_dir) / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    report_path = state_dir / "adoption-report.json"
    _ = report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(report_path)
