# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

import warnings

from runtime.cost_governor import CostGovernor, GovernorLimits


def test_initial_status_ok() -> None:
    gov = CostGovernor()
    status = gov.check_status()
    assert status.ok is True
    assert status.tokens_pct == 0.0
    assert status.cost_pct == 0.0


def test_record_tracks_usage() -> None:
    gov = CostGovernor()
    gov.record(tokens_in=1000, tokens_out=500, cost_usd=0.001)
    summary = gov.get_summary()
    assert summary["tokens_in"] == 1000
    assert summary["tokens_out"] == 500
    assert summary["api_calls"] == 1
    assert abs(summary["cost_usd"] - 0.001) < 0.0001


def test_token_limit_exceeded() -> None:
    gov = CostGovernor(
        limits=GovernorLimits(max_tokens=100, max_cost_usd=100.0, max_time_secs=9999)
    )
    status = gov.record(tokens_in=60, tokens_out=60)
    assert status.ok is False
    assert len(status.violations) > 0


def test_cost_limit_exceeded() -> None:
    gov = CostGovernor(
        limits=GovernorLimits(max_tokens=999999, max_cost_usd=0.01, max_time_secs=9999)
    )
    status = gov.record(tokens_in=0, tokens_out=0, cost_usd=0.02)
    assert status.ok is False


def test_warning_at_80pct() -> None:
    gov = CostGovernor(
        limits=GovernorLimits(max_tokens=100, max_cost_usd=100.0, max_time_secs=9999)
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        status = gov.record(tokens_in=45, tokens_out=40)
    resource_warnings = [
        item for item in caught if issubclass(item.category, ResourceWarning)
    ]
    assert len(resource_warnings) > 0 or len(status.warnings) > 0


def test_get_summary_has_required_fields() -> None:
    gov = CostGovernor()
    summary = gov.get_summary()
    assert "tokens_total" in summary
    assert "cost_usd" in summary
    assert "wall_time_secs" in summary
    assert "api_calls" in summary
    assert "limits" in summary


def test_multiple_records_accumulate() -> None:
    gov = CostGovernor()
    gov.record(tokens_in=100, cost_usd=0.001)
    gov.record(tokens_in=200, cost_usd=0.002)
    summary = gov.get_summary()
    assert summary["tokens_in"] == 300
    assert summary["api_calls"] == 2
    assert abs(summary["cost_usd"] - 0.003) < 0.0001
