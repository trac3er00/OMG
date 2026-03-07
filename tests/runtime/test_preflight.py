from __future__ import annotations

from runtime.preflight import run_preflight


def test_preflight_routes_security_work_to_security_check(tmp_path):
    result = run_preflight(str(tmp_path), goal="stabilize auth flow and verify secrets handling")
    assert result["schema"] == "PreflightResult"
    assert result["route"] == "security-check"
    assert result["risk_class"] == "high"
    assert "omg-control" in result["required_mcps"]


def test_preflight_routes_contract_work_to_api_twin(tmp_path):
    result = run_preflight(str(tmp_path), goal="ingest OpenAPI contract and replay offline fixtures")
    assert result["route"] == "api-twin"
    assert result["task_class"] == "contract"
