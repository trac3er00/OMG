from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast

_MODULES = (
    "verification_controller",
    "release_run_coordinator",
    "interaction_journal",
    "context_engine",
    "defense_state",
    "session_health",
    "council_verdicts",
    "rollback_manifest",
    "release_run",
)

_STATUS_VALUES = frozenset({"pending", "running", "ok", "error", "blocked"})

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]


class SchemaVersion(TypedDict):
    schema_name: str
    version: str
    required_fields: list[str]


def default_layout(project_dir: str) -> dict[str, dict[str, str]]:
    root = Path(project_dir)
    paths = {
        module: str(root / ".omg" / "state" / module)
        for module in _MODULES
    }
    return {"paths": paths}


def schema_versions() -> dict[str, SchemaVersion]:
    base_required = ["schema", "schema_version", "run_id", "status", "updated_at"]
    return {
        "verification_controller": {
            "schema_name": "VerificationControllerState",
            "version": "1.0.0",
            "required_fields": base_required + ["blockers", "evidence_links", "progress"],
        },
        "release_run_coordinator": {
            "schema_name": "ReleaseRunCoordinatorState",
            "version": "1.0.0",
            "required_fields": base_required + ["phase", "resolution_source", "resolution_reason"],
        },
        "interaction_journal": {
            "schema_name": "InteractionJournalState",
            "version": "1.0.0",
            "required_fields": base_required + ["events"],
        },
        "context_engine": {
            "schema_name": "ContextEngineState",
            "version": "1.0.0",
            "required_fields": base_required + ["artifacts", "context"],
        },
        "defense_state": {
            "schema_name": "DefenseState",
            "version": "1.0.0",
            "required_fields": base_required + ["controls", "findings"],
        },
        "session_health": {
            "schema_name": "SessionHealth",
            "version": "1.0.0",
            "required_fields": base_required + [
                "contamination_risk",
                "overthinking_score",
                "context_health",
                "verification_status",
                "recommended_action",
            ],
        },
        "council_verdicts": {
            "schema_name": "CouncilVerdicts",
            "version": "1.0.0",
            "required_fields": base_required + ["verdicts", "verification_status"],
        },
        "rollback_manifest": {
            "schema_name": "RollbackManifest",
            "version": "1.0.0",
            "required_fields": base_required + [
                "step_id",
                "local_restores",
                "compensating_actions",
                "side_effects",
            ],
        },
        "release_run": {
            "schema_name": "ReleaseRunState",
            "version": "1.0.0",
            "required_fields": base_required + [
                "phase",
                "resolution_source",
                "resolution_reason",
                "release_evidence",
                "health_action",
            ],
        },
    }


def make_run_path(project_dir: str, module: str, run_id: str) -> Path:
    _validate_module(module)
    return Path(project_dir) / ".omg" / "state" / module / f"{run_id}.json"


def write_run_state(project_dir: str, module: str, run_id: str, payload: dict[str, object]) -> str:
    path = make_run_path(project_dir, module, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    state = _normalize_payload(module, run_id, cast(JsonObject, payload))
    tmp_path = path.with_name(f"{path.name}.tmp")
    _ = tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")
    _ = os.rename(tmp_path, path)
    latest_path = path.parent / "latest.json"
    latest_tmp_path = latest_path.with_name("latest.json.tmp")
    _ = latest_tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")
    _ = os.rename(latest_tmp_path, latest_path)
    return str(path)


def read_run_state(project_dir: str, module: str, run_id: str) -> JsonObject | None:
    path = make_run_path(project_dir, module, run_id)
    payload = _read_payload(path)
    if payload is not None:
        return payload

    if module == "verification_controller":
        return _read_background_verification_compat(Path(project_dir), run_id)
    return None


def read_defense_state(
    project_dir: str,
    run_id: str | None = None,
    *,
    compat: bool = False,
) -> JsonObject | None:
    root = Path(project_dir)
    active_run_id = _resolve_active_run_id(root, run_id)
    if active_run_id:
        payload = _read_payload(root / ".omg" / "state" / "defense_state" / f"{active_run_id}.json")
        if payload is not None:
            return payload

    payload = _read_payload(root / ".omg" / "state" / "defense_state" / "current.json")
    if payload is not None:
        return payload

    if compat or not active_run_id:
        return _read_payload(root / ".omg" / "state" / "defense_state" / "latest.json")
    return None


def read_session_health(
    project_dir: str,
    run_id: str | None = None,
    *,
    compat: bool = False,
) -> JsonObject | None:
    root = Path(project_dir)
    active_run_id = _resolve_active_run_id(root, run_id)
    if active_run_id:
        payload = _read_payload(root / ".omg" / "state" / "session_health" / f"{active_run_id}.json")
        if payload is not None:
            return payload

    if compat or not active_run_id:
        return _read_payload(root / ".omg" / "state" / "session_health" / "latest.json")
    return None


def read_context_packet(project_dir: str, *, compat: bool = False) -> JsonObject | None:
    root = Path(project_dir)
    payload = _read_payload(root / ".omg" / "state" / "context_engine_packet.json")
    if payload is not None:
        return payload
    if compat:
        return _read_payload(root / ".omg" / "state" / "context_engine" / "latest.json")
    return None


def read_council_verdicts(
    project_dir: str,
    run_id: str | None = None,
    *,
    compat: bool = False,
) -> JsonObject | None:
    root = Path(project_dir)
    active_run_id = _resolve_active_run_id(root, run_id)
    if active_run_id:
        payload = _read_payload(root / ".omg" / "state" / "council_verdicts" / f"{active_run_id}.json")
        if payload is not None:
            return payload

    if compat or not active_run_id:
        return _read_payload(root / ".omg" / "state" / "council_verdicts" / "latest.json")
    return None


def _normalize_payload(module: str, run_id: str, payload: JsonObject) -> JsonObject:
    metadata = schema_versions()[module]
    state = dict(payload)
    state["schema"] = _to_str(state.get("schema"), metadata["schema_name"])
    state["schema_version"] = _to_str(state.get("schema_version"), metadata["version"])
    state["run_id"] = run_id

    status = _to_str(state.get("status"), "pending")
    state["status"] = status if status in _STATUS_VALUES else "error"
    state["updated_at"] = _to_str(state.get("updated_at"), datetime.now(timezone.utc).isoformat())
    return state


def _resolve_active_run_id(project_dir: Path, run_id: str | None) -> str:
    candidate = _to_str(run_id, "").strip()
    if candidate:
        return candidate

    candidate = os.environ.get("OMG_RUN_ID", "").strip()
    if candidate:
        return candidate

    active_run_path = project_dir / ".omg" / "shadow" / "active-run"
    if active_run_path.exists():
        try:
            candidate = active_run_path.read_text(encoding="utf-8").strip()
        except OSError:
            candidate = ""
        if candidate:
            return candidate

    for path in (
        project_dir / ".omg" / "state" / "defense_state" / "current.json",
        project_dir / ".omg" / "state" / "context_engine_packet.json",
    ):
        payload = _read_payload(path)
        if payload is None:
            continue
        candidate = _to_str(payload.get("run_id"), "").strip()
        if candidate:
            return candidate
    return ""


def _read_payload(path: Path) -> JsonObject | None:
    if not path.exists():
        return None
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return cast(JsonObject, payload)


def _read_background_verification_compat(project_dir: Path, run_id: str) -> JsonObject | None:
    compat_path = project_dir / ".omg" / "state" / "background-verification.json"
    payload = _read_payload(compat_path)
    if payload is None:
        return None
    if payload.get("schema") != "BackgroundVerificationState":
        return None
    if _to_str(payload.get("run_id"), "") != run_id:
        return None

    compat_payload = dict(payload)
    compat_payload["schema"] = "VerificationControllerState"
    compat_payload["schema_version"] = "1.0.0"
    status = _to_str(compat_payload.get("status"), "error")
    compat_payload["status"] = status if status in _STATUS_VALUES else "error"
    return compat_payload


def _validate_module(module: str) -> None:
    if module not in _MODULES:
        raise ValueError(f"unsupported state module: {module}")


def _to_str(value: JsonValue | None, default: str) -> str:
    if isinstance(value, str):
        return value
    return default
