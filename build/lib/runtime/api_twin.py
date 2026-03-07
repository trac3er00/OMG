"""Fixture-based API twin state and replay helpers."""
from __future__ import annotations

import json
import re
from pathlib import Path
import time
from typing import Any


STATE_REL_PATH = Path(".omg") / "state" / "api_twin.json"

DEFAULT_FRESHNESS_WINDOW_HOURS = 24

_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(authorization|auth|token|api[_-]?key|password|passwd|secret|bearer|credential)",
    re.IGNORECASE,
)

_METHOD_COST_WEIGHTS: dict[str, float] = {
    "GET": 1.0,
    "POST": 2.0,
    "PUT": 1.5,
    "PATCH": 1.5,
    "DELETE": 1.0,
    "HEAD": 0.5,
    "OPTIONS": 0.5,
}

_BASE_CALL_COST = 0.002


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
    endpoint: str = "default",
    cassette_version: str = "v1",
    request: dict[str, Any],
    response: dict[str, Any],
    validated: bool,
    redactions: dict[str, str] | None = None,
    freshness_window_hours: float = DEFAULT_FRESHNESS_WINDOW_HOURS,
    schema: dict[str, Any] | None = None,
    endpoint_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = _load_state(project_dir)

    redacted_request = redact_sensitive(request)
    redacted_response = redact_sensitive(response)

    now = time.time()
    freshness_metadata = {
        "recorded_at": now,
        "freshness_window_hours": freshness_window_hours,
        "is_stale": False,
    }

    recorded_schema = schema if schema else _derive_schema(response)
    ep_meta = endpoint_metadata or _parse_endpoint_metadata(endpoint)

    fixture = {
        "name": name,
        "endpoint": endpoint,
        "cassette_version": cassette_version,
        "request": redacted_request,
        "response": redacted_response,
        "fidelity": "recorded-validated" if validated else "recorded",
        "validated": validated,
        "redactions": redactions or {},
        "freshness_metadata": freshness_metadata,
        "schema": recorded_schema,
        "endpoint_metadata": ep_meta,
        "schema_drifted": False,
        "proof_chain": {},
    }
    fixtures = state.setdefault("fixtures", {}).setdefault(name, {})
    fixtures[_fixture_key(endpoint, cassette_version)] = fixture
    _save_state(project_dir, state)
    return {
        "schema": "ApiTwinFixture",
        "name": name,
        "endpoint": endpoint,
        "cassette_version": cassette_version,
        "fidelity": fixture["fidelity"],
        "freshness_metadata": freshness_metadata,
    }


def serve_fixture(
    project_dir: str,
    *,
    name: str,
    endpoint: str = "default",
    cassette_version: str = "v1",
    latency_ms: int = 0,
    failure_mode: str = "",
    schema_drift: bool = False,
) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = _fixture(state, name, endpoint=endpoint, cassette_version=cassette_version)
    response = dict(fixture.get("response", {}))
    fidelity = str(fixture.get("fidelity", "recorded"))

    freshness = fixture.get("freshness_metadata", {})
    if freshness and _is_stale(freshness):
        fidelity = "stale"

    if latency_ms > 0:
        time.sleep(max(latency_ms, 0) / 1000)
    if schema_drift:
        response["__schema_drift__"] = True
        fidelity = "stale"
    if failure_mode:
        response = {"error": failure_mode}
        fidelity = "stale"

    ep_meta = fixture.get("endpoint_metadata", {})
    cost_report = _compute_saved_cost(ep_meta)

    return {
        "schema": "ApiTwinServeResult",
        "name": name,
        "endpoint": endpoint,
        "cassette_version": cassette_version,
        "latency_ms": latency_ms,
        "failure_mode": failure_mode,
        "fidelity": fidelity,
        "response": response,
        "report": {
            "saved_live_calls": 1,
            "saved_cost_estimate": cost_report["saved_cost_estimate"],
            "cost_method": "endpoint_metadata",
            "redactions": fixture.get("redactions", {}),
        },
    }


def verify_fixture(
    project_dir: str,
    *,
    name: str,
    endpoint: str = "default",
    cassette_version: str = "v1",
    live_response: dict[str, Any],
) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = _fixture(state, name, endpoint=endpoint, cassette_version=cassette_version)
    matches_live = fixture.get("response", {}) == live_response

    freshness = fixture.get("freshness_metadata", {})
    is_stale = _is_stale(freshness) if freshness else False

    fidelity = "recorded-validated" if (matches_live and not is_stale) else "stale"

    fixture["fidelity"] = fidelity
    fixture["validated"] = matches_live

    if matches_live and not is_stale and freshness:
        freshness["recorded_at"] = time.time()
        freshness["is_stale"] = False
        fixture["freshness_metadata"] = freshness

    state.setdefault("fixtures", {}).setdefault(name, {})[_fixture_key(endpoint, cassette_version)] = fixture
    _save_state(project_dir, state)
    return {
        "schema": "ApiTwinVerifyResult",
        "name": name,
        "endpoint": endpoint,
        "cassette_version": cassette_version,
        "fidelity": fidelity,
        "matches_live": matches_live,
        "live_verification_required": True,
    }


def verify_endpoint(
    project_dir: str,
    *,
    name: str,
    endpoint: str = "default",
    cassette_version: str = "v1",
    live_response: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = _fixture(state, name, endpoint=endpoint, cassette_version=cassette_version)

    recorded_response = fixture.get("response", {})
    matches_live = recorded_response == live_response

    check_schema = schema or fixture.get("schema", {})
    schema_drifted = False
    drift_details: list[str] = []

    if check_schema and isinstance(check_schema, dict):
        required_fields = check_schema.get("required_fields", [])
        for field in required_fields:
            if field not in live_response:
                schema_drifted = True
                drift_details.append(f"missing_field:{field}")

        expected_types = check_schema.get("field_types", {})
        for field, expected_type in expected_types.items():
            if field in live_response:
                actual_type = type(live_response[field]).__name__
                if actual_type != expected_type:
                    schema_drifted = True
                    drift_details.append(f"type_mismatch:{field}:{expected_type}->{actual_type}")

    freshness = fixture.get("freshness_metadata", {})
    is_stale = _is_stale(freshness) if freshness else False

    if schema_drifted:
        fidelity = "schema-drifted"
    elif is_stale:
        fidelity = "stale"
    elif matches_live:
        fidelity = "recorded-validated"
    else:
        fidelity = "stale"

    production_proven = matches_live and not schema_drifted and not is_stale

    fixture["fidelity"] = fidelity
    fixture["validated"] = matches_live and not schema_drifted
    fixture["schema_drifted"] = schema_drifted

    if matches_live and not schema_drifted and freshness:
        freshness["recorded_at"] = time.time()
        freshness["is_stale"] = False
        fixture["freshness_metadata"] = freshness

    state.setdefault("fixtures", {}).setdefault(name, {})[_fixture_key(endpoint, cassette_version)] = fixture
    _save_state(project_dir, state)

    ep_meta = fixture.get("endpoint_metadata", {})

    return {
        "schema": "ApiTwinEndpointVerifyResult",
        "name": name,
        "endpoint": endpoint,
        "cassette_version": cassette_version,
        "fidelity": fidelity,
        "matches_live": matches_live,
        "schema_drifted": schema_drifted,
        "drift_details": drift_details,
        "is_stale": is_stale,
        "production_proven": production_proven,
        "live_verification_required": True,
        "endpoint_metadata": ep_meta,
        "report": {
            "endpoint": endpoint,
            "fidelity": fidelity,
            "production_proven": production_proven,
            "schema_drifted": schema_drifted,
            "drift_details": drift_details,
            "freshness": freshness,
            "saved_cost": _compute_saved_cost(ep_meta),
        },
    }


def redact_sensitive(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if _SENSITIVE_KEY_PATTERNS.search(key):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_sensitive(value)
        elif isinstance(value, list):
            redacted[key] = [redact_sensitive(item) if isinstance(item, dict) else item for item in value]
        else:
            redacted[key] = value
    return redacted


def saved_cost_report(
    project_dir: str,
    *,
    name: str,
    endpoint: str = "default",
    cassette_version: str = "v1",
) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = _fixture(state, name, endpoint=endpoint, cassette_version=cassette_version)
    ep_meta = fixture.get("endpoint_metadata", {})
    cost = _compute_saved_cost(ep_meta)
    return {
        "schema": "ApiTwinSavedCostReport",
        "name": name,
        "endpoint": endpoint,
        "cassette_version": cassette_version,
        "endpoint_metadata": ep_meta,
        **cost,
    }


def link_proof_chain(
    project_dir: str,
    *,
    name: str,
    endpoint: str = "default",
    cassette_version: str = "v1",
    trace_id: str,
    eval_id: str = "",
) -> dict[str, Any]:
    state = _load_state(project_dir)
    fixture = _fixture(state, name, endpoint=endpoint, cassette_version=cassette_version)
    proof_chain = {
        "trace_id": trace_id,
        "eval_id": eval_id,
        "linked_at": time.time(),
    }
    fixture["proof_chain"] = proof_chain
    state.setdefault("fixtures", {}).setdefault(name, {})[_fixture_key(endpoint, cassette_version)] = fixture
    _save_state(project_dir, state)
    return {
        "schema": "ApiTwinProofChainLink",
        "name": name,
        "endpoint": endpoint,
        "cassette_version": cassette_version,
        "proof_chain": proof_chain,
    }


def _state_path(project_dir: str) -> Path:
    return Path(project_dir) / STATE_REL_PATH


def _load_state(project_dir: str) -> dict[str, Any]:
    path = _state_path(project_dir)
    if not path.exists():
        return {"schema": "ApiTwinState", "version": "2.0.7", "contracts": {}, "fixtures": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": "ApiTwinState", "version": "2.0.7", "contracts": {}, "fixtures": {}}
    if not isinstance(payload, dict):
        return {"schema": "ApiTwinState", "version": "2.0.7", "contracts": {}, "fixtures": {}}
    payload.setdefault("schema", "ApiTwinState")
    payload.setdefault("version", "2.0.7")
    payload.setdefault("contracts", {})
    payload.setdefault("fixtures", {})
    return payload


def _save_state(project_dir: str, payload: dict[str, Any]) -> None:
    path = _state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _fixture_key(endpoint: str, cassette_version: str) -> str:
    return f"{endpoint}::{cassette_version}"


def _fixture(
    state: dict[str, Any],
    name: str,
    *,
    endpoint: str = "default",
    cassette_version: str = "v1",
) -> dict[str, Any]:
    fixtures = state.get("fixtures", {})
    if not isinstance(fixtures, dict) or name not in fixtures:
        raise ValueError(f"Unknown API twin fixture: {name}")
    fixture_group = fixtures[name]
    if not isinstance(fixture_group, dict):
        raise ValueError(f"Invalid API twin fixture: {name}")
    fixture = fixture_group.get(_fixture_key(endpoint, cassette_version))
    if not isinstance(fixture, dict):
        raise ValueError(f"Unknown API twin cassette: {name} {endpoint} {cassette_version}")
    return fixture


def _is_stale(freshness: dict[str, Any]) -> bool:
    recorded_at = freshness.get("recorded_at", 0)
    window_hours = freshness.get("freshness_window_hours", DEFAULT_FRESHNESS_WINDOW_HOURS)
    if not recorded_at:
        return True
    age_hours = (time.time() - recorded_at) / 3600
    return age_hours > window_hours


def _derive_schema(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    required_fields = list(response.keys())
    field_types = {k: type(v).__name__ for k, v in response.items()}
    return {
        "required_fields": required_fields,
        "field_types": field_types,
    }


def _parse_endpoint_metadata(endpoint: str) -> dict[str, Any]:
    parts = endpoint.strip().split(None, 1)
    if len(parts) == 2:
        method, path = parts
    elif len(parts) == 1:
        method, path = "GET", parts[0]
    else:
        method, path = "GET", endpoint

    method = method.upper()
    path_segments = [s for s in path.split("/") if s]
    avg_tokens = max(50, len(path_segments) * 100)

    return {
        "method": method,
        "path": path,
        "avg_tokens": avg_tokens,
    }


def _compute_saved_cost(ep_meta: dict[str, Any]) -> dict[str, Any]:
    method = ep_meta.get("method", "GET").upper()
    avg_tokens = ep_meta.get("avg_tokens", 50)
    method_weight = _METHOD_COST_WEIGHTS.get(method, 1.0)
    token_cost = avg_tokens * 0.00001
    saved_cost_estimate = round(_BASE_CALL_COST * method_weight + token_cost, 6)
    return {
        "saved_cost_estimate": saved_cost_estimate,
        "cost_method": "endpoint_metadata",
        "method_weight": method_weight,
        "avg_tokens": avg_tokens,
    }
