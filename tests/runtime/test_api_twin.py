from __future__ import annotations

from pathlib import Path

from runtime.api_twin import (
    ingest_contract,
    record_fixture,
    serve_fixture,
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
