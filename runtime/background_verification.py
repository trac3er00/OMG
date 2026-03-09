from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKGROUND_VERIFICATION_REL_PATH = Path(".omg") / "state" / "background-verification.json"

_VALID_STATUSES = frozenset({"running", "ok", "error", "blocked"})


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


def read_verification_state(project_dir: str) -> dict[str, Any] | None:
    path = Path(project_dir) / BACKGROUND_VERIFICATION_REL_PATH
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("schema") == "BackgroundVerificationState":
            return payload
    except (json.JSONDecodeError, OSError):
        pass
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
    - ``None``, empty, or unknown profiles fall back to FULL_REQUIREMENTS (no skip).
    - For other profiles, a stage is skipped when it is NOT in that profile's
      requirement list.
    """
    from runtime.evidence_requirements import requirements_for_profile

    profile = (evidence_profile or "").strip()

    # Never-skip profiles: full requirements, nothing skippable
    if profile in _NEVER_SKIP_PROFILES:
        return False

    required = requirements_for_profile(profile if profile else None)
    return stage not in required


def skipped_stages_for_profile(evidence_profile: str | None) -> list[str]:
    """Return the list of stages that WOULD be skipped for a given profile.

    Useful for logging and HUD state.
    """
    from runtime.evidence_requirements import FULL_REQUIREMENTS

    return [stage for stage in FULL_REQUIREMENTS if should_skip_validation(evidence_profile, stage)]


def run_validation_with_timeout(
    fn: object,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Execute a validation callable with a timeout gate.

    Returns a dict with ``status`` (the callable's return or ``"timeout"``)
    and ``timed_out`` bool.  The callable must be a zero-arg function
    returning a string status.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)  # type: ignore[arg-type]
        try:
            result = future.result(timeout=timeout_seconds)
            return {"status": result, "timed_out": False}
        except concurrent.futures.TimeoutError:
            future.cancel()
            return {"status": "timeout", "timed_out": True}
