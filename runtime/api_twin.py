"""Fixture-based API twin state and replay helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STATE_REL_PATH = Path(".omg") / "state" / "api_twin.json"


def ingest_contract(project_dir: str, *, name: str, source_path: str) -> dict[str, Any]:
    state = _load_state(project_dir)
    contract_path = Path(source_path)
    contract = {
        "name": name,
        "source_path": str(contract_path),
        "content": contract_path.read_text(encoding="utf-8"),
        "fidelity": "schema-only",
    }
    state.setdefault("contracts", {})[name] = contract
    _save_state(project_dir, state)
    return {
        "schema": "ApiTwinContract",
        "name": name,
        "fidelity": "schema-only",
        "source_path": str(contract_path),
    }


def record_fixture(
    project_dir: str,
    *,
    name: str,
    request: dict[str, Any],
    response: dict[str, Any],
    validated: bool,
) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = {
        "name": name,
        "request": request,
        "response": response,
        "fidelity": "recorded-validated" if validated else "recorded",
        "validated": validated,
    }
    state.setdefault("fixtures", {})[name] = fixture
    _save_state(project_dir, state)
    return {
        "schema": "ApiTwinFixture",
        "name": name,
        "fidelity": fixture["fidelity"],
    }


def serve_fixture(
    project_dir: str,
    *,
    name: str,
    latency_ms: int = 0,
    failure_mode: str = "",
    schema_drift: bool = False,
) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = _fixture(state, name)
    response = dict(fixture.get("response", {}))
    fidelity = str(fixture.get("fidelity", "recorded"))
    if schema_drift:
        response["__schema_drift__"] = True
        fidelity = "stale"
    if failure_mode:
        response = {"error": failure_mode}
        fidelity = "stale"
    return {
        "schema": "ApiTwinServeResult",
        "name": name,
        "latency_ms": latency_ms,
        "failure_mode": failure_mode,
        "fidelity": fidelity,
        "response": response,
    }


def verify_fixture(project_dir: str, *, name: str, live_response: dict[str, Any]) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = _fixture(state, name)
    matches_live = fixture.get("response", {}) == live_response
    fidelity = "recorded-validated" if matches_live else "stale"
    fixture["fidelity"] = fidelity
    fixture["validated"] = matches_live
    state.setdefault("fixtures", {})[name] = fixture
    _save_state(project_dir, state)
    return {
        "schema": "ApiTwinVerifyResult",
        "name": name,
        "fidelity": fidelity,
        "matches_live": matches_live,
        "live_verification_required": True,
    }


def _state_path(project_dir: str) -> Path:
    return Path(project_dir) / STATE_REL_PATH


def _load_state(project_dir: str) -> dict[str, Any]:
    path = _state_path(project_dir)
    if not path.exists():
        return {"contracts": {}, "fixtures": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"contracts": {}, "fixtures": {}}
    return payload if isinstance(payload, dict) else {"contracts": {}, "fixtures": {}}


def _save_state(project_dir: str, payload: dict[str, Any]) -> None:
    path = _state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _fixture(state: dict[str, Any], name: str) -> dict[str, Any]:
    fixtures = state.get("fixtures", {})
    if not isinstance(fixtures, dict) or name not in fixtures:
        raise ValueError(f"Unknown API twin fixture: {name}")
    fixture = fixtures[name]
    if not isinstance(fixture, dict):
        raise ValueError(f"Invalid API twin fixture: {name}")
    return fixture
