"""Tests for multi-dimensional budget envelopes (Task 6).

Scenarios:
  1. Worker stays inside all envelopes — healthy artifact, no escalation.
  2. Envelope breach triggers enforcement — wall-time or network limit exceeded.
  3. Envelope state persisted and retrievable.
  4. Governance action escalation — warn → reflect → block.
  5. Uncapped dimensions never breach.
  6. Pressure ratios for health integration.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from runtime.budget_envelopes import (
    BudgetEnvelope,
    BudgetEnvelopeManager,
    BudgetEnvelopeState,
    EnvelopeCheckResult,
    get_budget_envelope_manager,
)


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture()
def mgr(tmp_path: Path) -> BudgetEnvelopeManager:
    """Create a BudgetEnvelopeManager rooted at tmp_path."""
    return get_budget_envelope_manager(str(tmp_path))


# ═══════════════════════════════════════════════════════════
# Test 1: Worker stays inside all envelopes
# ═══════════════════════════════════════════════════════════


class TestHealthyEnvelope:
    """Worker runs entirely within limits — no governance escalation."""

    def test_within_limits_returns_ok(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope(
            "run-ok",
            cpu_seconds_limit=60.0,
            memory_mb_limit=512.0,
            wall_time_seconds_limit=300.0,
            token_limit=100_000,
            network_bytes_limit=10_000_000,
        )
        mgr.record_usage(
            "run-ok",
            cpu_seconds=10.0,
            memory_mb=128.0,
            wall_time_seconds=30.0,
            tokens=5_000,
            network_bytes=500_000,
        )

        result = mgr.check_envelope("run-ok")

        assert result.status == "ok"
        assert result.governance_action == "warn"  # no-op sentinel
        assert result.breached_dimensions == []
        assert "within limits" in result.reason

    def test_no_envelope_returns_ok(self, mgr: BudgetEnvelopeManager) -> None:
        result = mgr.check_envelope("nonexistent")
        assert result.status == "ok"
        assert "no envelope found" in result.reason

    def test_usage_accumulates_additively(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-accum", cpu_seconds_limit=100.0, token_limit=10_000)

        mgr.record_usage("run-accum", cpu_seconds=10.0, tokens=1_000)
        mgr.record_usage("run-accum", cpu_seconds=15.0, tokens=2_000)

        state = mgr.get_envelope_state("run-accum")
        assert state is not None
        usage = state["usage"]
        assert usage["cpu_seconds_used"] == 25.0
        assert usage["tokens_used"] == 3_000


# ═══════════════════════════════════════════════════════════
# Test 2: Envelope breach triggers enforcement
# ═══════════════════════════════════════════════════════════


class TestEnvelopeBreach:
    """Breaching a limit triggers governance block."""

    def test_wall_time_breach_triggers_block(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-wt", wall_time_seconds_limit=60.0)
        mgr.record_usage("run-wt", wall_time_seconds=61.0)

        result = mgr.check_envelope("run-wt")

        assert result.status == "breach"
        assert result.governance_action == "block"
        assert "wall_time" in result.breached_dimensions

    def test_network_breach_triggers_block(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-net", network_bytes_limit=1_000_000)
        mgr.record_usage("run-net", network_bytes=1_500_000)

        result = mgr.check_envelope("run-net")

        assert result.status == "breach"
        assert result.governance_action == "block"
        assert "network" in result.breached_dimensions

    def test_multiple_dimensions_breach(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope(
            "run-multi",
            cpu_seconds_limit=10.0,
            token_limit=1_000,
        )
        mgr.record_usage("run-multi", cpu_seconds=15.0, tokens=1_500)

        result = mgr.check_envelope("run-multi")

        assert result.status == "breach"
        assert result.governance_action == "block"
        assert "cpu" in result.breached_dimensions
        assert "tokens" in result.breached_dimensions

    def test_budget_simulate_enforce_semantic_maps_to_breach_block(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-enforce", token_limit=5)
        mgr.record_usage("run-enforce", tokens=6)

        result = mgr.check_envelope("run-enforce")

        assert result.status == "breach"
        assert result.governance_action == "block"
        assert "tokens" in result.breached_dimensions

    def test_memory_peak_tracking(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-mem", memory_mb_limit=256.0)
        mgr.record_usage("run-mem", memory_mb=100.0)
        mgr.record_usage("run-mem", memory_mb=200.0)
        # Lower usage doesn't reduce peak
        mgr.record_usage("run-mem", memory_mb=50.0)

        state = mgr.get_envelope_state("run-mem")
        assert state is not None
        assert state["usage"]["memory_mb_peak"] == 200.0


# ═══════════════════════════════════════════════════════════
# Test 3: Envelope state persisted and retrievable
# ═══════════════════════════════════════════════════════════


class TestStatePersistence:
    """Envelope state survives read/write roundtrip."""

    def test_create_persists_to_disk(self, mgr: BudgetEnvelopeManager, tmp_path: Path) -> None:
        mgr.create_envelope(
            "run-persist",
            cpu_seconds_limit=30.0,
            wall_time_seconds_limit=120.0,
        )

        json_path = tmp_path / ".omg" / "state" / "budget-envelopes" / "run-persist.json"
        assert json_path.exists()

        raw = json.loads(json_path.read_text(encoding="utf-8"))
        assert raw["schema"] == "BudgetEnvelopeState"
        assert raw["envelope"]["cpu_seconds_limit"] == 30.0
        assert raw["envelope"]["wall_time_seconds_limit"] == 120.0

    def test_get_envelope_state_returns_full_payload(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-read", token_limit=50_000)
        mgr.record_usage("run-read", tokens=12_000)

        state = mgr.get_envelope_state("run-read")
        assert state is not None
        assert state["schema"] == "BudgetEnvelopeState"
        assert state["envelope"]["token_limit"] == 50_000
        assert state["usage"]["tokens_used"] == 12_000

    def test_get_envelope_state_returns_none_for_missing(self, mgr: BudgetEnvelopeManager) -> None:
        assert mgr.get_envelope_state("does-not-exist") is None

    def test_check_results_recorded_in_history(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-hist", cpu_seconds_limit=100.0)
        mgr.record_usage("run-hist", cpu_seconds=50.0)
        mgr.check_envelope("run-hist")

        state = mgr.get_envelope_state("run-hist")
        assert state is not None
        assert len(state["checks"]) == 1
        assert state["checks"][0]["status"] == "ok"

    def test_cross_run_state_is_not_reused(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-a", token_limit=1)
        mgr.record_usage("run-a", tokens=2)
        run_a = mgr.check_envelope("run-a")
        run_b = mgr.check_envelope("run-b")

        assert run_a.status == "breach"
        assert run_a.governance_action == "block"
        assert run_b.status == "ok"
        assert run_b.reason == "no envelope found"


# ═══════════════════════════════════════════════════════════
# Test 4: Governance action escalation (warn → reflect → block)
# ═══════════════════════════════════════════════════════════


class TestGovernanceEscalation:
    """Governance actions escalate from warn through reflect to block."""

    def test_warn_at_80_percent(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-esc", cpu_seconds_limit=100.0)
        mgr.record_usage("run-esc", cpu_seconds=85.0)

        result = mgr.check_envelope("run-esc")

        assert result.status == "warn"
        assert result.governance_action == "warn"
        assert "cpu" in result.breached_dimensions

    def test_reflect_on_repeated_warning(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-reflect", cpu_seconds_limit=100.0)
        mgr.record_usage("run-reflect", cpu_seconds=85.0)

        # First check → warn
        r1 = mgr.check_envelope("run-reflect")
        assert r1.governance_action == "warn"

        # Second check with same dimension still warned → reflect
        r2 = mgr.check_envelope("run-reflect")
        assert r2.governance_action == "reflect"
        assert "repeated" in r2.reason

    def test_block_on_full_breach(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-block", cpu_seconds_limit=100.0)
        mgr.record_usage("run-block", cpu_seconds=101.0)

        result = mgr.check_envelope("run-block")

        assert result.status == "breach"
        assert result.governance_action == "block"

    def test_full_escalation_sequence(self, mgr: BudgetEnvelopeManager) -> None:
        """Walk through: ok → warn → reflect → block as usage grows."""
        mgr.create_envelope("run-full", wall_time_seconds_limit=100.0)

        # Phase 1: Under 80% → ok
        mgr.record_usage("run-full", wall_time_seconds=50.0)
        r1 = mgr.check_envelope("run-full")
        assert r1.status == "ok"

        # Phase 2: At 85% → warn
        mgr.record_usage("run-full", wall_time_seconds=35.0)
        r2 = mgr.check_envelope("run-full")
        assert r2.status == "warn"
        assert r2.governance_action == "warn"

        # Phase 3: Still at 85% → reflect (repeated warning)
        r3 = mgr.check_envelope("run-full")
        assert r3.governance_action == "reflect"

        # Phase 4: Over 100% → block
        mgr.record_usage("run-full", wall_time_seconds=20.0)
        r4 = mgr.check_envelope("run-full")
        assert r4.status == "breach"
        assert r4.governance_action == "block"


# ═══════════════════════════════════════════════════════════
# Test 5: Uncapped dimensions never breach
# ═══════════════════════════════════════════════════════════


class TestUncappedDimensions:
    """Zero limits mean uncapped — usage is tracked but never breaches."""

    def test_zero_limit_never_breaches(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-uncap")  # All limits 0
        mgr.record_usage(
            "run-uncap",
            cpu_seconds=9999.0,
            memory_mb=99999.0,
            wall_time_seconds=99999.0,
            tokens=9_999_999,
            network_bytes=999_999_999,
        )

        result = mgr.check_envelope("run-uncap")
        assert result.status == "ok"
        assert result.breached_dimensions == []

    def test_partial_limits_only_check_limited_dimensions(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-partial", token_limit=1_000)
        mgr.record_usage(
            "run-partial",
            cpu_seconds=99999.0,
            tokens=500,
        )

        result = mgr.check_envelope("run-partial")
        assert result.status == "ok"


# ═══════════════════════════════════════════════════════════
# Test 6: Pressure ratios for health integration
# ═══════════════════════════════════════════════════════════


class TestPressureRatios:
    """get_envelope_pressure returns per-dimension usage ratios."""

    def test_pressure_ratios_correct(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope(
            "run-press",
            cpu_seconds_limit=100.0,
            token_limit=10_000,
        )
        mgr.record_usage("run-press", cpu_seconds=50.0, tokens=7_500)

        pressure = mgr.get_envelope_pressure("run-press")
        assert pressure["cpu"] == 0.5
        assert pressure["tokens"] == 0.75

    def test_pressure_empty_for_missing_envelope(self, mgr: BudgetEnvelopeManager) -> None:
        pressure = mgr.get_envelope_pressure("nonexistent")
        assert pressure == {}

    def test_pressure_skips_uncapped_dimensions(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.create_envelope("run-skip", cpu_seconds_limit=100.0)
        mgr.record_usage("run-skip", cpu_seconds=50.0, tokens=99999)

        pressure = mgr.get_envelope_pressure("run-skip")
        assert "cpu" in pressure
        assert "tokens" not in pressure


# ═══════════════════════════════════════════════════════════
# Test 7: Auto-create envelope on record_usage
# ═══════════════════════════════════════════════════════════


class TestAutoCreate:
    """record_usage auto-creates an uncapped envelope if none exists."""

    def test_auto_create_on_usage(self, mgr: BudgetEnvelopeManager) -> None:
        mgr.record_usage("run-auto", tokens=500)

        state = mgr.get_envelope_state("run-auto")
        assert state is not None
        assert state["usage"]["tokens_used"] == 500
        # All limits should be 0 (uncapped)
        assert state["envelope"]["token_limit"] == 0


# ═══════════════════════════════════════════════════════════
# Test 8: Dataclass construction
# ═══════════════════════════════════════════════════════════


class TestDataclasses:
    """BudgetEnvelope, BudgetEnvelopeState, EnvelopeCheckResult are well-formed."""

    def test_budget_envelope_defaults(self) -> None:
        env = BudgetEnvelope(run_id="test")
        assert env.cpu_seconds_limit == 0.0
        assert env.memory_mb_limit == 0.0
        assert env.token_limit == 0

    def test_envelope_state_defaults(self) -> None:
        state = BudgetEnvelopeState(run_id="test")
        assert state.cpu_seconds_used == 0.0
        assert state.tokens_used == 0

    def test_check_result_defaults(self) -> None:
        result = EnvelopeCheckResult(status="ok")
        assert result.breached_dimensions == []
        assert result.governance_action == "warn"
