from __future__ import annotations

from runtime.preflight import run_preflight


def test_preflight_routes_security_work_to_security_check(tmp_path):
    result = run_preflight(str(tmp_path), goal="stabilize auth flow and verify secrets handling")
    assert result["schema"] == "PreflightResult"
    assert result["route"] == "security-check"
    assert result["risk_class"] == "high"
    assert result["requires_security_check"] is True
    assert "omg-control" in result["required_mcps"]


def test_preflight_routes_contract_work_to_api_twin(tmp_path):
    result = run_preflight(str(tmp_path), goal="ingest OpenAPI contract and replay offline fixtures")
    assert result["route"] == "api-twin"
    assert result["task_class"] == "contract"


def test_preflight_auto_triggers_security_for_infra_and_manifest_deltas(tmp_path):
    (tmp_path / "infra").mkdir(parents=True, exist_ok=True)
    (tmp_path / "infra" / "deploy.tf").write_text("resource \"aws_security_group\" \"x\" {}\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    result = run_preflight(str(tmp_path), goal="small docs cleanup")

    assert result["requires_security_check"] is True
    assert result["route"] == "security-check"
