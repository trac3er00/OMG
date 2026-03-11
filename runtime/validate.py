"""Canonical validation engine — composes doctor, contract, profile, and install checks.

This module is the single entrypoint for ``omg validate``.  It delegates to
existing checkers (``run_doctor``, ``validate_contract_registry``, profile
governor, install integrity) rather than duplicating their logic.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from runtime.adoption import CANONICAL_VERSION
from runtime.compat import run_doctor, _doctor_check
from runtime.contract_compiler import validate_contract_registry
from runtime.plugin_diagnostics import run_plugin_diagnostics
from runtime.profile_io import load_profile, ensure_governed_preferences, assess_profile_risk


def _check_contract_registry(root_dir: Path) -> dict[str, Any]:
    """Compose contract registry validation into a single doctor-style check."""
    try:
        result = validate_contract_registry(root_dir)
    except Exception as exc:
        return _doctor_check(
            "contract_registry",
            ok=False,
            message=f"contract validation error: {exc}",
        )
    if result.get("status") == "ok":
        error_count = len(result.get("errors", []))
        return _doctor_check(
            "contract_registry",
            ok=True,
            message=f"contract registry valid ({error_count} errors)",
        )
    errors = result.get("errors", [])
    summary = errors[0] if errors else "unknown error"
    if len(errors) > 1:
        summary += f" (+{len(errors) - 1} more)"
    return _doctor_check(
        "contract_registry",
        ok=False,
        message=f"contract registry invalid: {summary}",
    )


def _check_profile_governor(root_dir: Path) -> dict[str, Any]:
    """Validate that governed profile state is consistent."""
    profile_path = os.path.join(root_dir, ".omg", "state", "profile.yaml")
    profile = load_profile(profile_path)

    if not profile:
        return _doctor_check(
            "profile_governor",
            ok=True,
            message="no profile found (optional — run /OMG:init to create)",
            required=False,
        )

    try:
        ensure_governed_preferences(profile)
    except Exception as exc:
        return _doctor_check(
            "profile_governor",
            ok=False,
            message=f"governed preferences malformed: {exc}",
            required=False,
        )

    governed = profile.get("governed_preferences", {})
    governed = governed if isinstance(governed, dict) else {}
    style_entries = governed.get("style", [])
    style_entries = style_entries if isinstance(style_entries, list) else []
    safety_entries = governed.get("safety", [])
    safety_entries = safety_entries if isinstance(safety_entries, list) else []

    pending = sum(
        1 for e in style_entries + safety_entries
        if isinstance(e, dict) and e.get("confirmation_state") == "pending_confirmation"
    )

    risk = assess_profile_risk(profile)
    risk_level = str(risk.get("risk_level", "low"))

    parts = [f"{len(style_entries)} style, {len(safety_entries)} safety"]
    if pending:
        parts.append(f"{pending} pending confirmation")
    parts.append(f"risk={risk_level}")

    return _doctor_check(
        "profile_governor",
        ok=True,
        message=f"profile governor ok ({', '.join(parts)})",
        required=False,
    )


def _check_install_integrity(root_dir: Path) -> dict[str, Any]:
    """Verify critical install paths exist and are coherent."""
    issues: list[str] = []

    # Check scripts/omg.py exists
    omg_script = root_dir / "scripts" / "omg.py"
    if not omg_script.exists():
        issues.append("scripts/omg.py missing")

    # Check runtime/ package exists
    runtime_init = root_dir / "runtime" / "__init__.py"
    runtime_dir = root_dir / "runtime"
    if not runtime_dir.exists():
        issues.append("runtime/ directory missing")

    # Check commands/ directory exists
    commands_dir = root_dir / "commands"
    if not commands_dir.exists():
        issues.append("commands/ directory missing")

    # Check plugins/core/plugin.json exists
    plugin_json = root_dir / "plugins" / "core" / "plugin.json"
    if not plugin_json.exists():
        issues.append("plugins/core/plugin.json missing")

    # Check pyproject.toml exists
    pyproject = root_dir / "pyproject.toml"
    if not pyproject.exists():
        issues.append("pyproject.toml missing")

    if issues:
        return _doctor_check(
            "install_integrity",
            ok=False,
            message=f"install issues: {'; '.join(issues)}",
        )
    return _doctor_check(
        "install_integrity",
        ok=True,
        message="install integrity ok (scripts, runtime, commands, plugins present)",
    )


def _check_plugin_compatibility(root_dir: Path) -> dict[str, Any]:
    try:
        result = run_plugin_diagnostics(str(root_dir))
    except Exception as exc:
        return _doctor_check(
            "plugin_compatibility",
            ok=False,
            message=f"plugin diagnostics error: {exc}",
        )

    status = str(result.get("status", "error"))
    summary = result.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    total_records = int(summary.get("total_records", 0))
    total_conflicts = int(summary.get("total_conflicts", 0))
    blockers = int(summary.get("blockers", 0))

    return _doctor_check(
        "plugin_compatibility",
        ok=status in {"ok", "warn"},
        message=(
            f"plugin compatibility: {total_records} records, "
            f"{total_conflicts} conflicts, {blockers} blockers"
        ),
    )


def _load_selected_mcps(root_dir: Path) -> list[str]:
    """Load selected MCP IDs from cli-config.yaml.

    Checks CLAUDE_PROJECT_DIR env first, then falls back to root_dir.
    Returns an empty list when the config file is absent or unparseable.
    """
    import yaml as _yaml

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if project_dir:
        config_path = os.path.join(project_dir, ".omg", "state", "cli-config.yaml")
    else:
        config_path = os.path.join(root_dir, ".omg", "state", "cli-config.yaml")

    if not os.path.isfile(config_path):
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    mcps = data.get("selected_mcps", [])
    return [str(m) for m in mcps] if isinstance(mcps, list) else []


def _check_notebooklm(root_dir: Path) -> dict[str, Any] | None:
    """Optional NotebookLM health check — only runs when notebooklm is selected.

    Returns None when NotebookLM is not in the selected MCP set (meaning:
    skip entirely, no check emitted).  When selected, checks that ``npx``
    is reachable on PATH.  Missing npx is a *warning*, never a blocker.
    """
    selected = _load_selected_mcps(root_dir)
    if "notebooklm" not in selected:
        return None

    npx_path = shutil.which("npx")
    if npx_path is None:
        return _doctor_check(
            "notebooklm",
            ok=False,
            message="npx not found — install Node.js to use NotebookLM",
            required=False,
        )

    return _doctor_check(
        "notebooklm",
        ok=True,
        message="npx available, notebooklm-mcp callable",
        required=False,
    )


def run_validate(*, root_dir: Path | None = None) -> dict[str, Any]:
    """Run all validation checks and return a structured result.

    Composes:
    1. ``run_doctor()`` — install and runtime checks
    2. Contract registry validation
    3. Profile governor validation
    4. Install integrity check
    5. Optional NotebookLM check (only when selected in MCP config)

    Returns a dict matching the ``ValidateResult`` schema:
    ``{"schema": "ValidateResult", "status": "pass"|"fail", "checks": [...], "version": "..."}``
    """
    repo_root = root_dir or Path(__file__).resolve().parent.parent

    checks: list[dict[str, Any]] = []

    # 1. Compose doctor checks (never duplicate — delegate directly)
    doctor_result = run_doctor(root_dir=repo_root)
    checks.extend(doctor_result.get("checks", []))

    # 2. Contract registry
    checks.append(_check_contract_registry(repo_root))

    # 3. Profile governor
    checks.append(_check_profile_governor(repo_root))

    # 4. Install integrity
    checks.append(_check_install_integrity(repo_root))

    if not any(c.get("name") == "plugin_compatibility" for c in checks):
        checks.append(_check_plugin_compatibility(repo_root))

    nb_check = _check_notebooklm(repo_root)
    if nb_check is not None:
        checks.append(nb_check)

    has_blocker = any(c["status"] == "blocker" for c in checks)

    return {
        "schema": "ValidateResult",
        "status": "fail" if has_blocker else "pass",
        "checks": checks,
        "version": CANONICAL_VERSION,
    }


def format_text(result: dict[str, Any]) -> str:
    """Format a ValidateResult as human-readable text."""
    lines: list[str] = []
    for check in result.get("checks", []):
        if check["status"] == "ok":
            marker = "PASS"
        elif check["status"] == "blocker":
            marker = "BLOCKER"
        else:
            marker = "WARN"
        req_tag = "" if check.get("required", True) else " (optional)"
        lines.append(f"  {marker:>7} {check['name']}: {check['message']}{req_tag}")

    blockers = sum(1 for c in result.get("checks", []) if c["status"] == "blocker")
    warnings = sum(1 for c in result.get("checks", []) if c["status"] == "warning")
    passed = sum(1 for c in result.get("checks", []) if c["status"] == "ok")
    lines.append(f"\nPASS [{passed}] | WARN [{warnings}] | BLOCKER [{blockers}]")

    return "\n".join(lines)
