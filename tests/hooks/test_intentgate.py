"""Tests for intentgate-keyword-detector.py — Intent classification engine v1.2.

Tests confidence scoring, compound intent parsing, word boundary matching,
feature flag gating, and output format correctness.
"""
import json
import subprocess
import os
import pytest

# Project root for subprocess cwd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOK = "hooks/intentgate-keyword-detector.py"


def run_intentgate(message, enabled=True):
    """Run the intentgate hook via subprocess and return parsed JSON output."""
    payload = json.dumps({"user_message": message})
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = ROOT
    env["OAL_INTENTGATE_ENABLED"] = "1" if enabled else "0"

    proc = subprocess.run(
        ["python3", HOOK],
        input=payload,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"Non-zero exit: {proc.stderr}"
    stdout = (proc.stdout or "").strip()
    return json.loads(stdout) if stdout else {}


def get_intents(result):
    """Extract detected_intents list from result."""
    return result.get("LEADER_HINT", {}).get("detected_intents", [])


def intent_names(result):
    """Extract flat list of intent name strings from result."""
    return [i["intent"] for i in get_intents(result)]


# ═══════════════════════════════════════════════════════════
# 1. Single keyword → single intent + correct confidence
# ═══════════════════════════════════════════════════════════

class TestSingleKeyword:
    def test_single_keyword_detected(self):
        """Single keyword 'ultrawork fix bugs' → INTENT_MAX_EFFORT."""
        result = run_intentgate("ultrawork fix bugs")
        assert "INTENT_MAX_EFFORT" in intent_names(result)

    def test_single_keyword_has_confidence(self):
        """Detected intent includes confidence field."""
        result = run_intentgate("ultrawork fix bugs")
        intents = get_intents(result)
        assert len(intents) == 1
        assert "confidence" in intents[0]
        assert "keyword" in intents[0]
        assert intents[0]["keyword"] == "ultrawork"

    def test_standalone_exact_confidence(self):
        """Exact standalone keyword → 0.95 confidence."""
        result = run_intentgate("ultrawork")
        intents = get_intents(result)
        assert len(intents) == 1
        assert intents[0]["confidence"] == 0.95

    def test_context_embedded_confidence(self):
        """Keyword embedded in context → 0.90 confidence."""
        result = run_intentgate("let's tdd this feature")
        intents = get_intents(result)
        tdd = [i for i in intents if i["intent"] == "INTENT_TEST_DRIVEN"]
        assert len(tdd) == 1
        assert tdd[0]["confidence"] == 0.90

    @pytest.mark.parametrize("keyword,intent", [
        ("ultrawork", "INTENT_MAX_EFFORT"),
        ("autopilot", "INTENT_AUTONOMOUS"),
        ("ralph", "INTENT_LOOP"),
        ("tdd", "INTENT_TEST_DRIVEN"),
        ("search", "INTENT_SEARCH"),
        ("stop", "INTENT_STOP"),
        ("crazy", "INTENT_CRAZY"),
    ])
    def test_all_single_word_keywords(self, keyword, intent):
        """Each single-word keyword maps to correct intent."""
        result = run_intentgate(keyword)
        assert intent in intent_names(result)

    def test_multi_word_keyword_plan_this(self):
        """Multi-word keyword 'plan this' → INTENT_PLAN."""
        result = run_intentgate("plan this")
        assert "INTENT_PLAN" in intent_names(result)
        intents = get_intents(result)
        plan = [i for i in intents if i["intent"] == "INTENT_PLAN"]
        assert plan[0]["confidence"] == 0.95


# ═══════════════════════════════════════════════════════════
# 2. Multi-keyword → compound intents
# ═══════════════════════════════════════════════════════════

class TestCompoundIntent:
    def test_plan_and_tdd(self):
        """'plan this and tdd it' → both INTENT_PLAN + INTENT_TEST_DRIVEN."""
        result = run_intentgate("plan this and tdd it")
        names = intent_names(result)
        assert "INTENT_PLAN" in names
        assert "INTENT_TEST_DRIVEN" in names

    def test_compound_keyword_count(self):
        """Compound intent reports correct keyword_count."""
        result = run_intentgate("plan this and tdd it")
        hint = result.get("LEADER_HINT", {})
        assert hint.get("keyword_count") >= 2

    def test_compound_confidence_is_085(self):
        """Each intent in compound phrase → 0.85 confidence."""
        result = run_intentgate("plan this and tdd it")
        intents = get_intents(result)
        for intent in intents:
            assert intent["confidence"] == 0.85

    def test_triple_compound(self):
        """Three keywords → three intents all at 0.85."""
        result = run_intentgate("crazy autopilot ralph")
        names = intent_names(result)
        assert "INTENT_CRAZY" in names
        assert "INTENT_AUTONOMOUS" in names
        assert "INTENT_LOOP" in names
        intents = get_intents(result)
        for intent in intents:
            assert intent["confidence"] == 0.85


# ═══════════════════════════════════════════════════════════
# 3. Case-insensitive matching
# ═══════════════════════════════════════════════════════════

class TestCaseInsensitive:
    def test_uppercase_ultrawork(self):
        """'ULTRAWORK' → INTENT_MAX_EFFORT."""
        result = run_intentgate("ULTRAWORK")
        assert "INTENT_MAX_EFFORT" in intent_names(result)

    def test_mixed_case_tdd(self):
        """'TdD' → INTENT_TEST_DRIVEN."""
        result = run_intentgate("TdD")
        assert "INTENT_TEST_DRIVEN" in intent_names(result)

    def test_uppercase_plan_this(self):
        """'PLAN THIS' → INTENT_PLAN."""
        result = run_intentgate("PLAN THIS")
        assert "INTENT_PLAN" in intent_names(result)


# ═══════════════════════════════════════════════════════════
# 4. Word boundary matching
# ═══════════════════════════════════════════════════════════

class TestWordBoundary:
    def test_planning_no_trigger(self):
        """'planning this' does NOT trigger 'plan this'."""
        result = run_intentgate("planning this feature")
        assert "INTENT_PLAN" not in intent_names(result)

    def test_searching_no_trigger(self):
        """'searching' does NOT trigger 'search'."""
        result = run_intentgate("searching for files")
        assert "INTENT_SEARCH" not in intent_names(result)

    def test_research_no_trigger(self):
        """'research' does NOT trigger 'search'."""
        result = run_intentgate("do some research")
        assert "INTENT_SEARCH" not in intent_names(result)

    def test_stopping_no_trigger(self):
        """'stopping' does NOT trigger 'stop'."""
        result = run_intentgate("stopping the server")
        assert "INTENT_STOP" not in intent_names(result)

    def test_search_in_sentence_triggers(self):
        """'search for docs' DOES trigger 'search' (word boundary present)."""
        result = run_intentgate("search for docs")
        assert "INTENT_SEARCH" in intent_names(result)


# ═══════════════════════════════════════════════════════════
# 5. Feature flag disabled → returns {}
# ═══════════════════════════════════════════════════════════

class TestFeatureFlag:
    def test_disabled_returns_empty(self):
        """When OAL_INTENTGATE_ENABLED=0, returns {}."""
        result = run_intentgate("ultrawork fix bugs", enabled=False)
        assert result == {}

    def test_disabled_no_leader_hint(self):
        """Disabled flag → no LEADER_HINT even with keywords."""
        result = run_intentgate("crazy autopilot ralph", enabled=False)
        assert "LEADER_HINT" not in result


# ═══════════════════════════════════════════════════════════
# 6. No keyword → returns {}
# ═══════════════════════════════════════════════════════════

class TestNoKeyword:
    def test_normal_message_empty(self):
        """Normal message without keywords → {}."""
        result = run_intentgate("just a normal message")
        assert result == {}

    def test_empty_string_empty(self):
        """Empty string → {}."""
        result = run_intentgate("")
        assert result == {}

    def test_no_leader_hint(self):
        """No keywords → no LEADER_HINT key."""
        result = run_intentgate("hello world how are you")
        assert "LEADER_HINT" not in result


# ═══════════════════════════════════════════════════════════
# 7. Confidence always in [0.0, 1.0]
# ═══════════════════════════════════════════════════════════

class TestConfidenceRange:
    @pytest.mark.parametrize("prompt", [
        "ultrawork",
        "plan this and tdd it",
        "crazy autopilot ralph",
        "let's tdd this feature",
        "ultrawork and more ultrawork",
        "search for something then stop",
    ])
    def test_confidence_in_range(self, prompt):
        """All detected intents have confidence in [0.0, 1.0]."""
        result = run_intentgate(prompt)
        for intent in get_intents(result):
            assert 0.0 <= intent["confidence"] <= 1.0, \
                f"Out of range: {intent} for prompt '{prompt}'"


# ═══════════════════════════════════════════════════════════
# Additional: Multiple occurrences → 0.98 cap
# ═══════════════════════════════════════════════════════════

class TestMultipleOccurrences:
    def test_double_occurrence_098(self):
        """Same keyword twice → 0.98 confidence."""
        result = run_intentgate("ultrawork and more ultrawork")
        intents = get_intents(result)
        ultrawork = [i for i in intents if i["intent"] == "INTENT_MAX_EFFORT"]
        assert len(ultrawork) == 1
        assert ultrawork[0]["confidence"] == 0.98

    def test_triple_occurrence_still_098(self):
        """Same keyword three times → still 0.98 (capped)."""
        result = run_intentgate("tdd tdd tdd everywhere")
        intents = get_intents(result)
        tdd = [i for i in intents if i["intent"] == "INTENT_TEST_DRIVEN"]
        assert len(tdd) == 1
        assert tdd[0]["confidence"] == 0.98


# ═══════════════════════════════════════════════════════════
# Output format: classification_version, routing_enabled
# ═══════════════════════════════════════════════════════════

class TestOutputFormat:
    def test_classification_version(self):
        """Output includes classification_version '1.2'."""
        result = run_intentgate("ultrawork")
        hint = result.get("LEADER_HINT", {})
        assert hint.get("classification_version") == "1.2"

    def test_routing_enabled(self):
        """Output includes routing_enabled: True."""
        result = run_intentgate("ultrawork")
        hint = result.get("LEADER_HINT", {})
        assert hint.get("routing_enabled") is True

    def test_intent_dict_structure(self):
        """Each intent is a dict with intent, confidence, keyword keys."""
        result = run_intentgate("ultrawork")
        intents = get_intents(result)
        for intent in intents:
            assert set(intent.keys()) == {"intent", "confidence", "keyword"}

    def test_graceful_invalid_json(self):
        """Invalid JSON stdin → exit 0, no crash."""
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = ROOT
        env["OAL_INTENTGATE_ENABLED"] = "1"
        proc = subprocess.run(
            ["python3", HOOK],
            input="not json",
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
            check=False,
        )
        assert proc.returncode == 0
