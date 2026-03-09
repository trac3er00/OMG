"""Tests for runtime.context_engine — bounded context packet builder."""

import json
from pathlib import Path

from runtime.context_engine import ContextEngine


REQUIRED_KEYS = {"summary", "artifact_pointers", "budget", "delta_only", "run_id"}
BUDGET_KEYS = {"max_chars", "used_chars"}
CLARIFICATION_KEYS = {"requires_clarification", "intent_class", "clarification_prompt", "confidence"}


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_packet_has_required_keys(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-1")
    assert REQUIRED_KEYS.issubset(pkt.keys())
    assert "profile_digest" in pkt
    assert BUDGET_KEYS.issubset(pkt["budget"].keys())
    assert CLARIFICATION_KEYS.issubset(pkt["clarification_status"].keys())


def test_budget_respected(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "architecture_signal" / "latest.json",
        {"summary": "x" * 2000},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-2")
    assert pkt["budget"]["max_chars"] == 1000
    assert pkt["budget"]["used_chars"] <= 1000
    assert len(pkt["summary"]) <= 1000


def test_delta_only_flag_preserved(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-3", delta_only=True)
    assert pkt["delta_only"] is True


def test_delta_only_false_by_default(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-4")
    assert pkt["delta_only"] is False


def test_missing_state_files_degrade_gracefully(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-5")
    assert pkt["summary"] == "no context signals available"
    assert pkt["artifact_pointers"] == []
    assert pkt["budget"]["used_chars"] == 0
    assert pkt["run_id"] == "t-5"


def test_artifact_pointers_are_paths_not_content(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"risk_level": "low", "actions": []},
    )
    _write_json(
        tmp_path / ".omg" / "state" / ".context-pressure.json",
        {"tool_count": 42, "is_high": False},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-6")

    for ptr in pkt["artifact_pointers"]:
        assert isinstance(ptr, str)
        assert not ptr.startswith("{")
        assert "/" in ptr or "\\" in ptr


def test_summary_includes_defense_state(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"risk_level": "high", "actions": ["warn", "flag"]},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-7")
    assert "defense" in pkt["summary"]
    assert "high" in pkt["summary"]


def test_summary_includes_verification(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "background-verification.json",
        {"status": "running", "blockers": ["lint"]},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-8")
    assert "verification" in pkt["summary"]
    assert "running" in pkt["summary"]


def test_summary_includes_pressure(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / ".context-pressure.json",
        {"tool_count": 200, "is_high": True},
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-9")
    assert "pressure" in pkt["summary"]
    assert "200" in pkt["summary"]


def test_packet_persisted_to_disk(tmp_path):
    engine = ContextEngine(str(tmp_path))
    engine.build_packet(run_id="t-10")
    packet_path = tmp_path / ".omg" / "state" / "context_engine_packet.json"
    assert packet_path.exists()
    data = json.loads(packet_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "t-10"


def test_delta_only_no_change_reports_no_changes(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "defense_state" / "current.json",
        {"risk_level": "low", "actions": []},
    )
    engine = ContextEngine(str(tmp_path))
    engine.build_packet(run_id="t-11")
    pkt2 = engine.build_packet(run_id="t-11", delta_only=True)
    assert pkt2["delta_only"] is True
    assert "no changes" in pkt2["summary"]


def test_run_id_preserved(tmp_path):
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="my-custom-run-42")
    assert pkt["run_id"] == "my-custom-run-42"


def test_malformed_json_degrades(tmp_path):
    bad_path = tmp_path / ".omg" / "state" / "defense_state" / "current.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{invalid json!!!", encoding="utf-8")
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-12")
    assert "summary" in pkt
    assert isinstance(pkt["artifact_pointers"], list)


def test_packet_includes_clarification_status_from_intent_gate(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "intent_gate" / "t-13.json",
        {
            "requires_clarification": True,
            "intent_class": "ambiguous_config",
            "clarification_prompt": "Clarify provider and desired action.",
            "confidence": 0.93,
        },
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-13")
    status = pkt["clarification_status"]

    assert status["requires_clarification"] is True
    assert status["intent_class"] == "ambiguous_config"
    assert status["clarification_prompt"] == "Clarify provider and desired action."
    assert status["confidence"] == 0.93


def test_clarification_status_remains_bounded_and_budget_safe(tmp_path):
    _write_json(
        tmp_path / ".omg" / "state" / "intent_gate" / "t-14.json",
        {
            "requires_clarification": True,
            "intent_class": "ambiguous_config_with_extra_long_suffix_that_should_be_truncated",
            "clarification_prompt": "x" * 500,
            "confidence": "not-a-number",
        },
    )
    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-14")
    status = pkt["clarification_status"]

    assert len(status["clarification_prompt"]) <= 180
    assert len(status["intent_class"]) <= 48
    assert status["confidence"] == 0.0
    assert pkt["budget"]["used_chars"] <= pkt["budget"]["max_chars"]


def test_profile_digest_is_compact_and_bounded(tmp_path):
    profile_path = tmp_path / ".omg" / "state" / "profile.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        "\n".join(
            [
                "preferences:",
                "  architecture_requests:",
                "    - hexagonal architecture",
                "    - event sourcing",
                "    - CQRS",
                "    - graphql federation",
                "  constraints:",
                "    Keep Responses Stable: true",
                "    Timeout Seconds: 20",
                "    output format: JSON",
                "    max retries: 3",
                "    allow markdown: false",
                "    extra_rule: trim this",
                "user_vector:",
                "  tags:",
                "    - Reliability",
                "    - API Design",
                "    - Incident Response",
                "    - Deterministic Output",
                "    - Cost Control",
                "    - Excess",
                "  summary: This summary should be present and remain compact in packets.",
                "  confidence: 0.91",
                "profile_version: profile-v3",
            ]
        ),
        encoding="utf-8",
    )

    engine = ContextEngine(str(tmp_path))
    pkt = engine.build_packet(run_id="t-profile")
    digest = pkt["profile_digest"]

    assert digest["profile_version"] == "profile-v3"
    assert digest["confidence"] == 0.91
    assert len(digest["architecture_requests"]) == 3
    assert len(digest["constraints"]) == 5
    assert len(digest["tags"]) == 5
    assert len(digest["summary"]) <= 120
    assert pkt["budget"]["used_chars"] <= pkt["budget"]["max_chars"]
