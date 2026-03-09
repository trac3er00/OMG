from __future__ import annotations

import importlib

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


def test_preflight_docs_only_uses_docs_profile_requirements(tmp_path):
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    result = run_preflight(str(tmp_path), goal="update docs")

    registry = importlib.import_module("runtime.evidence_requirements")

    assert result["delta_classification"]["evidence_profile"] == "docs-only"
    assert result["evidence_requirements"] == registry.requirements_for_profile("docs-only")
    assert len(result["evidence_requirements"]) < len(registry.requirements_for_profile("code-change"))


def test_preflight_auto_triggers_security_for_policy_and_config_deltas(tmp_path):
    (tmp_path / "policy").mkdir(parents=True, exist_ok=True)
    (tmp_path / "policy" / "runtime-policy.yaml").write_text("allow_privilege_escalation: true\n", encoding="utf-8")
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "app-config.yaml").write_text("verify: false\n", encoding="utf-8")

    result = run_preflight(str(tmp_path), goal="small docs cleanup")

    assert result["requires_security_check"] is True
    assert result["route"] == "security-check"
