from __future__ import annotations
import os
import pytest

@pytest.fixture()
def production_env(monkeypatch):
    monkeypatch.setenv("OMG_PRESET", "production")
    monkeypatch.delenv("OMG_TDD_GATE_STRICT", raising=False)

@pytest.fixture()
def production_env_permissive(monkeypatch):
    monkeypatch.setenv("OMG_PRESET", "production")
    monkeypatch.setenv("OMG_TDD_GATE_STRICT", "0")

def test_production_preset_enables_test_generation(production_env):
    from hooks._common import get_feature_flag
    assert get_feature_flag("TEST_GENERATION") is True

def test_production_preset_enables_council_routing(production_env):
    from hooks._common import get_feature_flag
    assert get_feature_flag("COUNCIL_ROUTING") is True

def test_production_preset_enables_terms_enforcement(production_env):
    from hooks._common import get_feature_flag
    assert get_feature_flag("TERMS_ENFORCEMENT") is True

def test_production_preset_enables_data_enforcement(production_env):
    from hooks._common import get_feature_flag
    assert get_feature_flag("DATA_ENFORCEMENT") is True

def test_production_mutation_blocked_without_lock(tmp_path, production_env):
    from runtime.mutation_gate import check_mutation_allowed
    result = check_mutation_allowed("Edit", "src/app.py", str(tmp_path), lock_id=None, run_id="run-prod", metadata={})
    assert result["status"] == "blocked"
    assert result.get("reason") in ("no_active_test_intent_lock", "done_when_required", "tool_plan_required")

def test_production_read_allowed_without_lock(tmp_path, production_env):
    from runtime.mutation_gate import check_mutation_allowed
    result = check_mutation_allowed("Read", "src/app.py", str(tmp_path), lock_id=None, run_id=None, metadata={})
    assert result["status"] == "allowed"

def test_production_escape_hatch_works(tmp_path, production_env_permissive):
    from runtime.mutation_gate import check_mutation_allowed
    result = check_mutation_allowed("Bash", ".", str(tmp_path), lock_id=None, command="git status", run_id=None, metadata={})
    assert result["status"] == "allowed"

def test_production_proof_gate_returns_structured(production_env):
    from runtime.proof_gate import evaluate_proof_gate
    result = evaluate_proof_gate({"run_id": "run-prod-no-ev", "claims": []})
    assert isinstance(result, dict)
    assert result.get("verdict") in ("pass", "fail") or result.get("status") in ("ok", "missing", "incomplete", "error")
