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
