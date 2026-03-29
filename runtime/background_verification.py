from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

BACKGROUND_VERIFICATION_REL_PATH = Path(".omg") / "state" / "background-verification.json"

_VALID_STATUSES = frozenset({"running", "ok", "error", "blocked"})
_logger = logging.getLogger(__name__)


def publish_verification_state(
    project_dir: str,
    run_id: str,
    status: str,
    blockers: list[str],
    evidence_links: list[str],
    progress: dict[str, Any],
) -> str:
    state = {
        "schema": "BackgroundVerificationState",
        "schema_version": 2,
        "run_id": run_id,
        "status": status if status in _VALID_STATUSES else "error",
        "blockers": blockers,
        "evidence_links": evidence_links,
        "progress": progress,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    path = Path(project_dir) / BACKGROUND_VERIFICATION_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")
    return str(path)


def read_verification_state(project_dir: str, run_id: str | None = None) -> dict[str, Any] | None:
    path = Path(project_dir) / BACKGROUND_VERIFICATION_REL_PATH
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        if payload.get("schema") != "BackgroundVerificationState":
            return None
        if int(payload.get("schema_version", 0)) != 2:
            return None
        status = str(payload.get("status", "")).strip()
        if status not in _VALID_STATUSES:
            return None
        expected_run_id = str(run_id or "").strip()
        if expected_run_id and str(payload.get("run_id", "")).strip() != expected_run_id:
            return None
        return payload
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Failed to read background verification state: %s", exc, exc_info=True)
    return None


# --- Task 10: Smart validation skipping + timeout gates ---

# Profiles that must NEVER skip any validation stage.
_NEVER_SKIP_PROFILES: frozenset[str] = frozenset({"release", "security-audit"})


def should_skip_validation(evidence_profile: str | None, stage: str) -> bool:
    """Return True if *stage* can be skipped for the given evidence profile.

    Uses the central requirement registry from ``runtime.evidence_requirements``
    so profile names and requirement lists are never hardcoded here.

    Rules:
    - ``release`` and ``security-audit`` profiles NEVER skip any stage.
    - ``None`` or empty profiles use FULL_REQUIREMENTS (no skip).
    - Unknown profiles fail closed (no skip) — the error is surfaced by
      :func:`resolve_evidence_profile` instead.
    - For other profiles, a stage is skipped when it is NOT in that profile's
      requirement list.
    """
    from runtime.evidence_requirements import requirements_for_profile

    profile = (evidence_profile or "").strip()

    # Never-skip profiles: full requirements, nothing skippable
    if profile in _NEVER_SKIP_PROFILES:
        return False

    try:
        required = requirements_for_profile(profile if profile else None)
    except ValueError:
        # Unknown profile: fail closed — don't skip any validation
        return False
    return stage not in required


def resolve_evidence_profile(evidence_profile: str | None) -> dict[str, Any]:
    """Resolve an evidence profile with strict validation.

    Returns a structured dict:
    - Success: ``{"status": "ok", "profile": <canonical>, "requirements": [...]}``
    - Failure: ``{"status": "error", "reason": "unknown_profile", "profile": <raw>}``
    """
    from runtime.evidence_requirements import (
        FULL_REQUIREMENTS,
        resolve_profile,
        requirements_for_profile,
    )

    raw = (evidence_profile or "").strip()
    if not raw:
        return {
            "status": "ok",
            "profile": None,
            "requirements": list(FULL_REQUIREMENTS),
        }

    try:
        canonical = resolve_profile(raw)
        return {
            "status": "ok",
            "profile": canonical,
            "requirements": requirements_for_profile(raw),
        }
    except ValueError:
        return {
            "status": "error",
            "reason": "unknown_profile",
            "profile": raw,
        }


def skipped_stages_for_profile(evidence_profile: str | None) -> list[str]:
    """Return the list of stages that WOULD be skipped for a given profile.

    Useful for logging and HUD state.
    """
    from runtime.evidence_requirements import FULL_REQUIREMENTS

    return [stage for stage in FULL_REQUIREMENTS if should_skip_validation(evidence_profile, stage)]


def run_validation_with_timeout(
    fn: Callable[[], str],
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Execute a validation callable with a timeout gate.

    Returns a dict with ``status`` (the callable's return or ``"timeout"``)
    and ``timed_out`` bool.  The callable must be a zero-arg function
    returning a string status.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            result = future.result(timeout=timeout_seconds)
            return {"status": result, "timed_out": False}
        except concurrent.futures.TimeoutError:
            future.cancel()
            return {"status": "timeout", "timed_out": True}


def check_worker_stalls(project_dir: str) -> dict[str, Any]:
    """Check for stalled workers via WorkerWatchdog; returns stall summary with run_ids."""
    try:
        from runtime.worker_watchdog import get_worker_watchdog
        watchdog = get_worker_watchdog(project_dir)
        stalled = watchdog.get_stalled_workers()
        return {
            "stalled_count": len(stalled),
            "stalled_run_ids": [str(w.get("run_id", "")) for w in stalled],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return {"stalled_count": 0, "stalled_run_ids": [], "checked_at": datetime.now(timezone.utc).isoformat()}
