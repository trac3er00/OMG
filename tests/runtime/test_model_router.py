# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

import warnings

from runtime.model_router import ModelRouter, RoutingDecision


def test_trivial_task_routes_to_model():
    router = ModelRouter()
    decision = router.route(complexity="trivial")
    assert isinstance(decision, RoutingDecision)
    assert decision.model_id
    assert decision.complexity == "trivial"


def test_critical_task_gets_high_quality():
    router = ModelRouter()
    decision = router.route(complexity="critical")
    assert decision.model_id
    assert decision.reasoning


def test_routing_decision_logged():
    router = ModelRouter()
    router.route(complexity="simple")
    log = router.get_routing_log()
    assert len(log) == 1
    assert "model_id" in log[0]
    assert "reasoning" in log[0]
    assert "timestamp" in log[0]


def test_budget_warning_at_80pct():
    router = ModelRouter(session_budget=1.0)
    router.budget.consumed_usd = 0.82
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        router.route(complexity="trivial")
    budget_warnings = [
        item
        for item in caught
        if "BUDGET" in str(item.message) or "budget" in str(item.message).lower()
    ]
    assert budget_warnings, "Expected budget warning"


def test_record_usage_tracks_cost():
    router = ModelRouter(session_budget=10.0)
    router.record_usage(1000, cost_usd=0.003)
    status = router.get_budget_status()
    assert status["tokens_used"] == 1000
    assert status["api_calls"] == 1
    assert abs(status["consumed_usd"] - 0.003) < 0.001


def test_budget_status_structure():
    router = ModelRouter(session_budget=5.0)
    status = router.get_budget_status()
    assert "session_budget" in status
    assert "remaining_usd" in status
    assert "remaining_pct" in status
    assert "api_calls" in status
    assert status["session_budget"] == 5.0
