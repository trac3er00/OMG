"""Tests for magic-keyword-router.py — Intent-to-agent routing engine.

Tests routing decision logic, LEADER_HINT resolution from stdin and file,
feature flag gating, fallback behavior, and output schema correctness.
"""
import json
import os
import subprocess
import tempfile
import shutil
import pytest

# Project root for subprocess cwd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOK = "hooks/magic-keyword-router.py"
ROUTING_RESULT_REL = ".omg/state/routing_result.json"


def _make_leader_hint(intents):
    """Build a LEADER_HINT dict from a list of (intent, confidence, keyword) tuples."""
    return {
        "LEADER_HINT": {
            "detected_intents": [
                {"intent": intent, "confidence": conf, "keyword": kw}
                for intent, conf, kw in intents
            ],
            "keyword_count": len(intents),
            "routing_enabled": True,
            "classification_version": "1.2",
        }
    }


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with .omg/state."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    return tmp_path


def run_router(payload, project_dir=None, enabled=True):
    """Run the magic-keyword-router hook via subprocess and return parsed output + routing result."""
    stdin_data = json.dumps(payload)
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir) if project_dir else ROOT
    env["OMG_MAGIC_ROUTER_ENABLED"] = "1" if enabled else "0"

    proc = subprocess.run(
        ["python3", os.path.join(ROOT, HOOK)],
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"Non-zero exit: {proc.stderr}"
    stdout = (proc.stdout or "").strip()
    hook_output = json.loads(stdout) if stdout else {}

    # Read routing result file
    result_path = os.path.join(
        str(project_dir) if project_dir else ROOT,
        ROUTING_RESULT_REL,
    )
    routing_result = None
    if os.path.exists(result_path):
        with open(result_path, "r") as f:
            routing_result = json.load(f)

    return hook_output, routing_result


# ═══════════════════════════════════════════════════════════
# 1. Each intent maps to correct target agent
# ═══════════════════════════════════════════════════════════

class TestIntentRouting:
    @pytest.mark.parametrize("intent,keyword,expected_agent", [
        ("INTENT_MAX_EFFORT", "ultrawork", "sisyphus"),
        ("INTENT_AUTONOMOUS", "autopilot", "sisyphus"),
        ("INTENT_LOOP", "ralph", "sisyphus"),
        ("INTENT_PLAN", "plan this", "prometheus"),
        ("INTENT_TEST_DRIVEN", "tdd", "sisyphus"),
        ("INTENT_SEARCH", "search", "librarian"),
        ("INTENT_CRAZY", "crazy", "sisyphus"),
    ])
    def test_intent_routes_to_correct_agent(self, intent, keyword, expected_agent, tmp_project):
        """Each intent maps to the correct target agent."""
        payload = _make_leader_hint([(intent, 0.95, keyword)])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result is not None, "routing_result.json not written"
        assert result["target_agent"] == expected_agent
        assert result["intent"] == intent
        assert result["confidence"] == 0.95
        assert result["fallback"] is False

    def test_all_8_intents_routed(self, tmp_project):
        """Verify all intents from the routing table are handled."""
        from hooks._agent_registry import INTENT_ROUTING
        assert len(INTENT_ROUTING) == 12, f"Expected 12 intents, got {len(INTENT_ROUTING)}"
        for intent_name, expected_agent in INTENT_ROUTING.items():
            payload = _make_leader_hint([(intent_name, 0.90, "test")])
            _, result = run_router(payload, project_dir=tmp_project)
            assert result is not None
            assert result["target_agent"] == expected_agent
            assert result["intent"] == intent_name


# ═══════════════════════════════════════════════════════════
# 2. INTENT_STOP → target_agent: null
# ═══════════════════════════════════════════════════════════

class TestIntentStop:
    def test_stop_routes_to_null(self, tmp_project):
        """INTENT_STOP → target_agent is null (no agent dispatch)."""
        payload = _make_leader_hint([("INTENT_STOP", 0.95, "stop")])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result is not None
        assert result["target_agent"] is None
        assert result["intent"] == "INTENT_STOP"
        assert result["fallback"] is False

    def test_stop_confidence_preserved(self, tmp_project):
        """INTENT_STOP preserves confidence from LEADER_HINT."""
        payload = _make_leader_hint([("INTENT_STOP", 0.90, "stop")])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result["confidence"] == 0.90


# ═══════════════════════════════════════════════════════════
# 2.5. INTENT_CLARIFICATION → target_agent: null (Task 3)
# ═══════════════════════════════════════════════════════════

class TestIntentClarification:
    def test_clarification_routes_to_null(self, tmp_project):
        """INTENT_CLARIFICATION → target_agent is null (no mutation-capable dispatch)."""
        payload = _make_leader_hint([("INTENT_CLARIFICATION", 0.95, "clarification")])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result is not None
        assert result["target_agent"] is None
        assert result["intent"] == "INTENT_CLARIFICATION"
        assert result["fallback"] is False

    def test_clarification_confidence_preserved(self, tmp_project):
        """INTENT_CLARIFICATION preserves confidence from LEADER_HINT."""
        payload = _make_leader_hint([("INTENT_CLARIFICATION", 0.85, "clarification")])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result["confidence"] == 0.85

    def test_clarification_halts_execution(self, tmp_project):
        """Clarification intent halts execution (no agent dispatch, not fallback)."""
        payload = _make_leader_hint([("INTENT_CLARIFICATION", 0.90, "clarification")])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result is not None
        assert result["target_agent"] is None
        assert result["fallback"] is False  # Not a fallback — explicit halt


# ═══════════════════════════════════════════════════════════
# 3. No LEADER_HINT → fallback routing
# ═══════════════════════════════════════════════════════════

class TestFallbackRouting:
    def test_no_leader_hint_fallback(self, tmp_project):
        """No LEADER_HINT in input → fallback routing result."""
        _, result = run_router({}, project_dir=tmp_project)
        assert result is not None
        assert result["target_agent"] is None
        assert result["intent"] is None
        assert result["fallback"] is True

    def test_empty_detected_intents_fallback(self, tmp_project):
        """LEADER_HINT with empty detected_intents → fallback."""
        payload = {
            "LEADER_HINT": {
                "detected_intents": [],
                "keyword_count": 0,
                "routing_enabled": True,
                "classification_version": "1.2",
            }
        }
        _, result = run_router(payload, project_dir=tmp_project)
        assert result is not None
        assert result["fallback"] is True
        assert result["target_agent"] is None

    def test_no_stdin_reads_file(self, tmp_project):
        """When stdin has no LEADER_HINT, reads from .omg/state/leader_hint.json."""
        # Write leader_hint.json file
        hint_path = tmp_project / ".omg" / "state" / "leader_hint.json"
        hint_data = _make_leader_hint([("INTENT_PLAN", 0.90, "plan this")])
        with open(hint_path, "w") as f:
            json.dump(hint_data, f)

        # Provide empty stdin (no LEADER_HINT)
        _, result = run_router({}, project_dir=tmp_project)
        assert result is not None
        assert result["target_agent"] == "prometheus"
        assert result["intent"] == "INTENT_PLAN"
        assert result["fallback"] is False

    def test_stdin_preferred_over_file(self, tmp_project):
        """Stdin LEADER_HINT takes precedence over file."""
        # Write file with INTENT_PLAN
        hint_path = tmp_project / ".omg" / "state" / "leader_hint.json"
        file_data = _make_leader_hint([("INTENT_PLAN", 0.90, "plan this")])
        with open(hint_path, "w") as f:
            json.dump(file_data, f)

        # Provide stdin with INTENT_MAX_EFFORT
        stdin_data = _make_leader_hint([("INTENT_MAX_EFFORT", 0.95, "ultrawork")])
        _, result = run_router(stdin_data, project_dir=tmp_project)
        assert result is not None
        assert result["target_agent"] == "sisyphus"
        assert result["intent"] == "INTENT_MAX_EFFORT"


# ═══════════════════════════════════════════════════════════
# 4. Feature flag disabled → no routing result written
# ═══════════════════════════════════════════════════════════

class TestFeatureFlag:
    def test_disabled_no_routing_written(self, tmp_project):
        """When OMG_MAGIC_ROUTER_ENABLED=0, no routing_result.json is written."""
        payload = _make_leader_hint([("INTENT_MAX_EFFORT", 0.95, "ultrawork")])
        _, result = run_router(payload, project_dir=tmp_project, enabled=False)
        assert result is None, "routing_result.json should NOT be written when disabled"

    def test_disabled_returns_empty_output(self, tmp_project):
        """Disabled flag → hook returns {} on stdout."""
        payload = _make_leader_hint([("INTENT_CRAZY", 0.95, "crazy")])
        output, _ = run_router(payload, project_dir=tmp_project, enabled=False)
        assert output == {}


# ═══════════════════════════════════════════════════════════
# 5. Output JSON schema is correct
# ═══════════════════════════════════════════════════════════

class TestOutputSchema:
    def test_routing_result_schema_with_intent(self, tmp_project):
        """Routing result with intent has correct keys."""
        payload = _make_leader_hint([("INTENT_SEARCH", 0.90, "search")])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result is not None
        required_keys = {"target_agent", "intent", "confidence", "fallback", "timestamp"}
        assert set(result.keys()) == required_keys

    def test_routing_result_schema_fallback(self, tmp_project):
        """Fallback routing result has correct keys."""
        _, result = run_router({}, project_dir=tmp_project)
        assert result is not None
        required_keys = {"target_agent", "intent", "confidence", "fallback", "timestamp"}
        assert set(result.keys()) == required_keys

    def test_timestamp_is_iso_format(self, tmp_project):
        """Timestamp is ISO 8601 formatted string."""
        payload = _make_leader_hint([("INTENT_LOOP", 0.95, "ralph")])
        _, result = run_router(payload, project_dir=tmp_project)
        ts = result["timestamp"]
        assert isinstance(ts, str)
        assert "T" in ts  # ISO 8601 always contains T separator

    def test_confidence_is_float(self, tmp_project):
        """Confidence is a float value."""
        payload = _make_leader_hint([("INTENT_LOOP", 0.85, "ralph")])
        _, result = run_router(payload, project_dir=tmp_project)
        assert isinstance(result["confidence"], float)

    def test_hook_stdout_is_empty_dict(self, tmp_project):
        """Hook stdout output is always {} (no-op for PostToolUse)."""
        payload = _make_leader_hint([("INTENT_CRAZY", 0.95, "crazy")])
        output, _ = run_router(payload, project_dir=tmp_project)
        assert output == {}


# ═══════════════════════════════════════════════════════════
# 6. Compound intents (picks first routable)
# ═══════════════════════════════════════════════════════════

class TestCompoundIntents:
    def test_first_intent_wins(self, tmp_project):
        """With multiple intents, first one in list is selected."""
        payload = _make_leader_hint([
            ("INTENT_PLAN", 0.85, "plan this"),
            ("INTENT_TEST_DRIVEN", 0.85, "tdd"),
        ])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result["target_agent"] == "prometheus"
        assert result["intent"] == "INTENT_PLAN"

    def test_stop_first_still_routes_to_stop(self, tmp_project):
        """If INTENT_STOP is first, it wins even though target_agent is None."""
        payload = _make_leader_hint([
            ("INTENT_STOP", 0.95, "stop"),
            ("INTENT_MAX_EFFORT", 0.85, "ultrawork"),
        ])
        _, result = run_router(payload, project_dir=tmp_project)
        assert result["target_agent"] is None
        assert result["intent"] == "INTENT_STOP"


# ═══════════════════════════════════════════════════════════
# 7. Graceful error handling
# ═══════════════════════════════════════════════════════════

class TestErrorHandling:
    def test_invalid_json_stdin_exits_clean(self):
        """Invalid JSON stdin → exit 0, no crash."""
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = ROOT
        env["OMG_MAGIC_ROUTER_ENABLED"] = "1"
        proc = subprocess.run(
            ["python3", os.path.join(ROOT, HOOK)],
            input="not json",
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
            check=False,
        )
        assert proc.returncode == 0

    def test_corrupt_leader_hint_file_fallback(self, tmp_project):
        """Corrupt leader_hint.json → fallback routing (not crash)."""
        hint_path = tmp_project / ".omg" / "state" / "leader_hint.json"
        with open(hint_path, "w") as f:
            f.write("not valid json {{{")

        _, result = run_router({}, project_dir=tmp_project)
        assert result is not None
        assert result["fallback"] is True


# ═══════════════════════════════════════════════════════════
# 8. INTENT_ROUTING registry integrity
# ═══════════════════════════════════════════════════════════

class TestRegistryIntegrity:
    def test_intent_routing_has_8_entries(self):
        """INTENT_ROUTING dict has exactly 12 entries (8 original + 3 bundled from Task 2.3 + 1 clarification from Task 3)."""
        from hooks._agent_registry import INTENT_ROUTING
        assert len(INTENT_ROUTING) == 12

    def test_intent_routing_values_are_strings_or_none(self):
        """All values in INTENT_ROUTING are str or None."""
        from hooks._agent_registry import INTENT_ROUTING
        for intent, agent in INTENT_ROUTING.items():
            assert agent is None or isinstance(agent, str), \
                f"Invalid agent for {intent}: {agent!r}"

    def test_intent_routing_keys_match_keyword_map(self):
        """All intents in INTENT_ROUTING include original 8 plus bundled agent intents plus clarification."""
        from hooks._agent_registry import INTENT_ROUTING
        expected_intents = {
            "INTENT_MAX_EFFORT", "INTENT_AUTONOMOUS", "INTENT_LOOP",
            "INTENT_PLAN", "INTENT_TEST_DRIVEN", "INTENT_SEARCH",
            "INTENT_STOP", "INTENT_CRAZY",
            # Bundled agent intents (Task 2.3)
            "INTENT_EXPLORE", "INTENT_REVIEW", "INTENT_QUICK",
            # Clarification intent (Task 3)
            "INTENT_CLARIFICATION",
        }
        assert set(INTENT_ROUTING.keys()) == expected_intents
