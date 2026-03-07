from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from runtime.api_twin import (
    ingest_contract,
    link_proof_chain,
    record_fixture,
    redact_sensitive,
    saved_cost_report,
    serve_fixture,
    verify_endpoint,
    verify_fixture,
)


def test_api_twin_lifecycle(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")

    ingest = ingest_contract(str(tmp_path), name="demo", source_path=str(contract))
    assert ingest["fidelity"] == "schema-only"

    record = record_fixture(
        str(tmp_path),
        name="demo",
        request={"path": "/users"},
        response={"users": []},
        validated=False,
    )
    assert record["fidelity"] == "recorded"

    served = serve_fixture(str(tmp_path), name="demo", schema_drift=True)
    assert served["schema"] == "ApiTwinServeResult"
    assert served["fidelity"] == "stale"

    verified = verify_fixture(str(tmp_path), name="demo", live_response={"users": []})
    assert verified["fidelity"] == "recorded-validated"
    assert verified["live_verification_required"] is True


def test_freshness_window_marks_stale_cassette(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="fresh", source_path=str(contract))

    record_fixture(
        str(tmp_path),
        name="fresh",
        endpoint="GET /users",
        request={"path": "/users"},
        response={"users": ["alice"]},
        validated=True,
        freshness_window_hours=1,
    )

    two_hours_ago = time.time() - (2 * 3600)
    with patch("runtime.api_twin.time") as mock_time:
        mock_time.time.return_value = two_hours_ago
        mock_time.sleep = time.sleep
        stale_record = record_fixture(
            str(tmp_path),
            name="fresh",
            endpoint="GET /stale-users",
            request={"path": "/stale-users"},
            response={"users": ["bob"]},
            validated=True,
            freshness_window_hours=1,
        )

    assert stale_record["freshness_metadata"]["recorded_at"] == two_hours_ago

    verified = verify_fixture(
        str(tmp_path),
        name="fresh",
        endpoint="GET /stale-users",
        live_response={"users": ["bob"]},
    )
    assert verified["fidelity"] == "stale"


def test_schema_drift_downgrades_cassette(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="drift", source_path=str(contract))

    record_fixture(
        str(tmp_path),
        name="drift",
        endpoint="GET /users",
        request={"path": "/users"},
        response={"users": [], "total": 0},
        validated=True,
    )

    drifted_live = {"users": []}
    result = verify_endpoint(
        str(tmp_path),
        name="drift",
        endpoint="GET /users",
        live_response=drifted_live,
        schema={"required_fields": ["users", "total"], "field_types": {"total": "int"}},
    )

    assert result["schema_drifted"] is True
    assert result["fidelity"] == "schema-drifted"
    assert result["production_proven"] is False
    assert any("missing_field:total" in d for d in result["drift_details"])


def test_redaction_removes_sensitive_fields():
    payload = {
        "path": "/users",
        "authorization": "Bearer secret-token-123",
        "api_key": "sk-abc123",
        "headers": {
            "content-type": "application/json",
            "auth_token": "my-token",
        },
        "password": "hunter2",
        "data": [{"name": "alice"}, {"secret": "vault-key"}],
    }

    redacted = redact_sensitive(payload)

    assert redacted["path"] == "/users"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["headers"]["content-type"] == "application/json"
    assert redacted["headers"]["auth_token"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["data"][0]["name"] == "alice"
    assert redacted["data"][1]["secret"] == "[REDACTED]"


def test_redaction_applied_during_record(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="redact", source_path=str(contract))

    record_fixture(
        str(tmp_path),
        name="redact",
        request={"path": "/login", "authorization": "Bearer xyz"},
        response={"token": "secret-jwt", "status": "ok"},
        validated=False,
    )

    served = serve_fixture(str(tmp_path), name="redact")
    assert served["response"]["token"] == "[REDACTED]"
    assert served["response"]["status"] == "ok"


def test_saved_cost_uses_endpoint_metadata(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="cost", source_path=str(contract))

    record_fixture(
        str(tmp_path),
        name="cost",
        endpoint="POST /payments",
        request={"amount": 100},
        response={"id": "pay_123", "status": "ok"},
        validated=True,
    )

    report = saved_cost_report(str(tmp_path), name="cost", endpoint="POST /payments")

    assert report["schema"] == "ApiTwinSavedCostReport"
    assert report["cost_method"] == "endpoint_metadata"
    assert report["method_weight"] == 2.0
    assert report["avg_tokens"] == 100
    assert report["saved_cost_estimate"] > 0

    served = serve_fixture(str(tmp_path), name="cost", endpoint="POST /payments")
    assert served["report"]["cost_method"] == "endpoint_metadata"
    assert served["report"]["saved_cost_estimate"] > 0


def test_proof_chain_linkage(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="proof", source_path=str(contract))

    record_fixture(
        str(tmp_path),
        name="proof",
        endpoint="GET /health",
        request={"path": "/health"},
        response={"status": "ok"},
        validated=True,
    )

    result = link_proof_chain(
        str(tmp_path),
        name="proof",
        endpoint="GET /health",
        trace_id="trace-abc-123",
        eval_id="eval-def-456",
    )

    assert result["schema"] == "ApiTwinProofChainLink"
    assert result["proof_chain"]["trace_id"] == "trace-abc-123"
    assert result["proof_chain"]["eval_id"] == "eval-def-456"
    assert result["proof_chain"]["linked_at"] > 0


def test_endpoint_level_report(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="report", source_path=str(contract))

    record_fixture(
        str(tmp_path),
        name="report",
        endpoint="GET /users",
        request={"path": "/users"},
        response={"users": ["alice"], "count": 1},
        validated=True,
    )

    result = verify_endpoint(
        str(tmp_path),
        name="report",
        endpoint="GET /users",
        live_response={"users": ["alice"], "count": 1},
    )

    assert result["schema"] == "ApiTwinEndpointVerifyResult"
    assert result["production_proven"] is True
    assert result["fidelity"] == "recorded-validated"
    assert result["report"]["endpoint"] == "GET /users"
    assert result["report"]["production_proven"] is True
    assert result["report"]["saved_cost"]["cost_method"] == "endpoint_metadata"


def test_stale_cassette_cannot_be_production_proven(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="stale", source_path=str(contract))

    two_hours_ago = time.time() - (2 * 3600)
    with patch("runtime.api_twin.time") as mock_time:
        mock_time.time.return_value = two_hours_ago
        mock_time.sleep = time.sleep
        record_fixture(
            str(tmp_path),
            name="stale",
            endpoint="GET /data",
            request={"path": "/data"},
            response={"data": "value"},
            validated=True,
            freshness_window_hours=1,
        )

    result = verify_endpoint(
        str(tmp_path),
        name="stale",
        endpoint="GET /data",
        live_response={"data": "value"},
    )

    assert result["is_stale"] is True
    assert result["fidelity"] == "stale"
    assert result["production_proven"] is False


def test_schema_type_mismatch_causes_drift(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    ingest_contract(str(tmp_path), name="types", source_path=str(contract))

    record_fixture(
        str(tmp_path),
        name="types",
        endpoint="GET /items",
        request={"path": "/items"},
        response={"items": [], "count": 0},
        validated=True,
    )

    result = verify_endpoint(
        str(tmp_path),
        name="types",
        endpoint="GET /items",
        live_response={"items": [], "count": "zero"},
        schema={"required_fields": ["items", "count"], "field_types": {"count": "int"}},
    )

    assert result["schema_drifted"] is True
    assert result["production_proven"] is False
    assert any("type_mismatch:count" in d for d in result["drift_details"])
