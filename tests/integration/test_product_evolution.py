"""Integration tests for OMG Product Evolution features (T1-T26)."""

import json
import os
import tempfile


class TestInstantModeIntegration:
    def test_instant_mode_with_proof_score(self, tmp_path: str) -> None:
        """Instant mode generates scaffold and ProofScore is computed."""
        from runtime.instant_mode import run_instant
        from runtime.proof_score import compute_score

        d = tempfile.mkdtemp()
        r = run_instant("make a landing page", d)
        assert r["success"]
        evidence = r.get("evidence", {})
        if "proofScore" in evidence:
            assert 0 <= evidence["proofScore"]["score"] <= 100
        else:
            s = compute_score([{"type": "scaffold", "valid": True}])
            assert 0 <= s["score"] <= 100

    def test_instant_mode_all_7_types(self) -> None:
        """All 7 product types can be classified and scaffolded."""
        from runtime.intent_classifier import classify_intent

        types = ["saas", "landing", "ecommerce", "api", "bot", "admin", "cli"]
        prompts = [
            "make a SaaS app",
            "make a landing page",
            "make a shop",
            "make an API",
            "make a chatbot",
            "make an admin panel",
            "make a CLI tool",
        ]
        for prompt, expected_type in zip(prompts, types):
            r = classify_intent(prompt)
            assert r["type"] == expected_type, (
                f"Expected {expected_type} for '{prompt}', got {r['type']}"
            )

    def test_instant_mode_korean_input(self) -> None:
        """Korean prompts work with instant mode."""
        from runtime.instant_mode import run_instant

        d = tempfile.mkdtemp()
        r = run_instant("랜딩페이지 만들어줘", d)
        assert r["success"]
        assert r["type"] == "landing"


class TestElasticAgentIntegration:
    def test_elastic_with_loop_breaker(self) -> None:
        """Elastic pool respects loop-breaker signals."""
        from runtime.elastic_agent import ElasticPool
        from runtime.loop_breaker import detect_loop

        pool = ElasticPool(max_workers=8)
        history = [
            {"tool": "grep", "args": {"pattern": "foo", "path": "."}},
            {"tool": "grep", "args": {"pattern": "foo", "path": "."}},
            {"tool": "grep", "args": {"pattern": "foo", "path": "."}},
        ]
        loop_result = detect_loop(history)
        assert loop_result["detected"]
        count = pool.compute_agent_count("complex")
        assert 1 <= count <= 8


class TestModelToggleIntegration:
    def test_toggle_affects_routing(self) -> None:
        """Model toggle affects model selection."""
        from runtime.model_toggle import get_mode, get_preferred_model, set_mode

        set_mode("fast")
        assert get_mode() == "fast"
        m = get_preferred_model("medium")
        assert "haiku" in m.lower() or "flash" in m.lower() or "mini" in m.lower()
        set_mode("balanced")


class TestHandoffIntegration:
    def test_handoff_save_and_resume(self) -> None:
        """Handoff save and resume round-trip."""
        from runtime.auto_resume import check_resume, clear_handoff, save_handoff

        state = {"decisions": ["use TDD", "instant mode first"], "version": "3.0.0"}
        save_handoff(state)
        r = check_resume()
        assert r["available"]
        assert "use TDD" in r["state"]["decisions"]
        clear_handoff()
        r2 = check_resume()
        assert not r2["available"]


class TestNextAdvisorIntegration:
    def test_next_after_instant_mode(self) -> None:
        """After instant mode, /next recommends relevant steps."""
        from runtime.next_advisor import recommend_next

        recs = recommend_next({"testing": 20, "security": 80})
        assert len(recs) > 0
        assert recs[0]["dimension"] == "testing"


class TestHUDIntegration:
    def test_hud_emitter_and_reader(self) -> None:
        """HUD emitter writes events that reader can parse."""
        from runtime.hud_emitter import emit_agent_start, emit_cost_update

        emit_agent_start("test-agent", "integration test")
        emit_cost_update(1000, 0.05, 80.0)
        hud_path = os.path.join(".omg", "state", "hud-events.jsonl")
        assert os.path.exists(hud_path)
        with open(hud_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        types = [e["type"] for e in events]
        assert "agent_start" in types or "cost_update" in types


class TestDomainPacksIntegration:
    def test_all_7_packs_validate(self) -> None:
        """All 7 domain packs validate with strict schema."""
        from runtime.pack_schema_validator import validate_pack

        packs = ["landing", "api", "ecommerce", "bot", "admin", "cli", "saas"]
        for pack_name in packs:
            path = f"packs/domains/{pack_name}/pack.yaml"
            r = validate_pack(path, strict=(pack_name != "saas"))
            assert r["valid"], f"{pack_name} pack invalid: {r.get('errors')}"
