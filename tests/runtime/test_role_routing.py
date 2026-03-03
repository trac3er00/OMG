"""Tests for role-based routing in team_router.py (Task 2.2)."""
from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure imports work
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HOOKS_DIR = os.path.join(_ROOT, "hooks")
_AGENTS_DIR = os.path.join(_ROOT, "agents")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
if _AGENTS_DIR not in sys.path:
    sys.path.insert(0, _AGENTS_DIR)

from runtime.team_router import route_with_role, get_role_from_env


# =============================================================================
# get_role_from_env Tests
# =============================================================================


class TestGetRoleFromEnv:
    """Tests for get_role_from_env() helper."""

    def test_returns_none_when_not_set(self):
        """Returns None when OAL_ACTIVE_ROLE is not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OAL_ACTIVE_ROLE", None)
            assert get_role_from_env() is None

    def test_returns_role_when_set(self):
        """Returns role name when OAL_ACTIVE_ROLE is set."""
        with patch.dict(os.environ, {"OAL_ACTIVE_ROLE": "smol"}):
            assert get_role_from_env() == "smol"

    def test_lowercases_value(self):
        """Lowercases the env var value."""
        with patch.dict(os.environ, {"OAL_ACTIVE_ROLE": "SLOW"}):
            assert get_role_from_env() == "slow"

    def test_strips_whitespace(self):
        """Strips whitespace from value."""
        with patch.dict(os.environ, {"OAL_ACTIVE_ROLE": "  plan  "}):
            assert get_role_from_env() == "plan"

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        with patch.dict(os.environ, {"OAL_ACTIVE_ROLE": ""}):
            assert get_role_from_env() is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only string returns None."""
        with patch.dict(os.environ, {"OAL_ACTIVE_ROLE": "   "}):
            assert get_role_from_env() is None


# =============================================================================
# route_with_role — Feature Flag Disabled
# =============================================================================


class TestRouteWithRoleDisabled:
    """Tests for route_with_role() when feature flag is disabled."""

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "0"}, clear=False)
    def test_feature_flag_disabled_returns_baseline(self):
        """When ROLE_ROUTING disabled, returns baseline routing unchanged."""
        result = route_with_role("fix typo in README")
        assert result["role"] is None
        assert result["model"] is None
        assert "intent-based" in result["reason"]

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "false"}, clear=False)
    def test_feature_flag_false_returns_baseline(self):
        """String 'false' also disables."""
        result = route_with_role("fix auth middleware", role="slow")
        assert result["role"] is None
        assert result["model"] is None

    @patch.dict(os.environ, {}, clear=False)
    def test_feature_flag_not_set_returns_baseline(self):
        """Default (no env var) returns baseline since default=False."""
        os.environ.pop("OAL_ROLE_ROUTING_ENABLED", None)
        result = route_with_role("debug performance issue")
        assert result["role"] is None

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "0"}, clear=False)
    def test_disabled_preserves_provider_from_infer_target(self):
        """Disabled flag still uses _infer_target for provider field."""
        result = route_with_role("fix auth security issue")
        assert result["provider"] == "codex"
        assert result["role"] is None


# =============================================================================
# route_with_role — Feature Flag Enabled, Explicit Role
# =============================================================================


class TestRouteWithRoleEnabled:
    """Tests for route_with_role() with feature flag enabled and explicit role."""

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_smol_role_routes_to_haiku(self):
        """smol role routes to cheapest model (haiku-class)."""
        result = route_with_role("fix typo", role="smol")
        assert result["role"] == "smol"
        assert "haiku" in result["model"].lower()
        assert "role-based" in result["reason"]

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_slow_role_routes_to_opus(self):
        """slow role routes to most capable model (opus-class)."""
        result = route_with_role("complex architectural decision", role="slow")
        assert result["role"] == "slow"
        assert "opus" in result["model"].lower()

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_plan_role_routes_to_sonnet(self):
        """plan role routes to planning model (sonnet-class)."""
        result = route_with_role("plan the migration", role="plan")
        assert result["role"] == "plan"
        assert "sonnet" in result["model"].lower()

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_commit_role_routes_to_haiku(self):
        """commit role routes to concise model (haiku-class)."""
        result = route_with_role("write commit message", role="commit")
        assert result["role"] == "commit"
        assert "haiku" in result["model"].lower()

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_default_role_routes_to_opus(self):
        """default role routes to standard model."""
        result = route_with_role("general task", role="default")
        assert result["role"] == "default"
        assert result["model"] is not None

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_unknown_role_falls_back_to_default(self):
        """Unknown role falls back to default role config."""
        result = route_with_role("something", role="nonexistent_role_xyz")
        # get_role returns default when name not found
        assert result["role"] == "nonexistent_role_xyz"
        assert result["model"] is not None  # gets default role's model

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_result_has_required_keys(self):
        """Result dict always has model, provider, role, reason keys."""
        result = route_with_role("anything", role="smol")
        assert "model" in result
        assert "provider" in result
        assert "role" in result
        assert "reason" in result


# =============================================================================
# route_with_role — Role Resolution Priority
# =============================================================================


class TestRoleResolutionPriority:
    """Tests for role resolution: explicit > env var > CLI args."""

    @patch.dict(os.environ, {
        "OAL_ROLE_ROUTING_ENABLED": "1",
        "OAL_ACTIVE_ROLE": "slow",
    }, clear=False)
    def test_explicit_role_overrides_env_var(self):
        """Explicit role parameter takes priority over env var."""
        result = route_with_role("task", role="smol")
        assert result["role"] == "smol"
        assert "haiku" in result["model"].lower()

    @patch.dict(os.environ, {
        "OAL_ROLE_ROUTING_ENABLED": "1",
        "OAL_ACTIVE_ROLE": "plan",
    }, clear=False)
    def test_env_var_used_when_no_explicit_role(self):
        """Env var is used when no explicit role parameter."""
        with patch("sys.argv", ["program"]):
            result = route_with_role("task")
        assert result["role"] == "plan"
        assert "sonnet" in result["model"].lower()

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_cli_args_used_when_no_role_or_env(self):
        """CLI args used when no explicit role and no env var."""
        os.environ.pop("OAL_ACTIVE_ROLE", None)
        with patch("sys.argv", ["program", "--slow"]):
            result = route_with_role("task")
        assert result["role"] == "slow"
        assert "opus" in result["model"].lower()

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_no_role_anywhere_returns_baseline(self):
        """No role from any source returns baseline routing."""
        os.environ.pop("OAL_ACTIVE_ROLE", None)
        with patch("sys.argv", ["program"]):
            result = route_with_role("fix auth middleware")
        assert result["role"] is None
        assert result["model"] is None
        assert "intent-based" in result["reason"]


# =============================================================================
# Cost Optimization Verification
# =============================================================================


class TestCostOptimization:
    """Verify cost-aware routing: smol=cheapest, slow=most capable."""

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_smol_is_cheapest_model(self):
        """smol role uses the cheapest model (haiku-class)."""
        result = route_with_role("trivial fix", role="smol")
        assert "haiku" in result["model"].lower()

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_slow_is_most_capable(self):
        """slow role uses the most capable model (opus-class)."""
        result = route_with_role("complex reasoning task", role="slow")
        assert "opus" in result["model"].lower()

    @patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "1"}, clear=False)
    def test_commit_is_cheap_and_concise(self):
        """commit role uses cheap model with low token limit."""
        result = route_with_role("generate commit msg", role="commit")
        assert "haiku" in result["model"].lower()


# =============================================================================
# Existing Routing Unchanged
# =============================================================================


class TestExistingRoutingUnchanged:
    """Ensure existing functions are not broken by new code."""

    def test_infer_target_still_works(self):
        """_infer_target still returns correct targets."""
        from runtime.team_router import _infer_target
        assert _infer_target("fix auth security") == "codex"
        assert _infer_target("ui layout responsive") == "gemini"
        assert _infer_target("full-stack architecture") == "ccg"

    def test_dispatch_team_still_works(self):
        """dispatch_team still returns TeamDispatchResult."""
        from runtime.team_router import dispatch_team, TeamDispatchRequest
        req = TeamDispatchRequest(target="auto", problem="fix auth bug")
        result = dispatch_team(req)
        assert result.status == "ok"
        assert len(result.findings) > 0

    def test_route_with_role_baseline_matches_infer_target(self):
        """Baseline (no role) uses _infer_target result as provider."""
        with patch.dict(os.environ, {"OAL_ROLE_ROUTING_ENABLED": "0"}, clear=False):
            result = route_with_role("fix ui layout issue")
        from runtime.team_router import _infer_target
        expected = _infer_target("fix ui layout issue")
        assert result["provider"] == expected
