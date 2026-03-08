from __future__ import annotations

from runtime import equalizer


def test_select_provider_prefers_gemini_for_ui_tasks(monkeypatch):
    monkeypatch.setattr(equalizer, "_probe_provider", lambda _provider: (True, True, "ok"))
    out = equalizer.select_provider(task_text="review responsive UI layout", project_dir=".")
    assert out["provider"] == "gemini"
    assert out["domain_fit"] == "ui_frontend"
    assert "reason" in out


def test_select_provider_prefers_codex_for_refactor_tasks(monkeypatch):
    monkeypatch.setattr(equalizer, "_probe_provider", lambda _provider: (True, True, "ok"))
    out = equalizer.select_provider(task_text="refactor backend api module", project_dir=".")
    assert out["provider"] == "codex"
    assert out["domain_fit"] == "code_refactor"


def test_select_provider_prefers_claude_for_complex_architecture(monkeypatch):
    monkeypatch.setattr(equalizer, "_probe_provider", lambda _provider: (True, True, "ok"))
    out = equalizer.select_provider(task_text="complex architecture tradeoff for distributed system", project_dir=".")
    assert out["provider"] == "claude"
    assert out["domain_fit"] == "complex_architecture"


def test_select_provider_prefers_kimi_for_fast_simple(monkeypatch):
    monkeypatch.setattr(equalizer, "_probe_provider", lambda _provider: (True, True, "ok"))
    out = equalizer.select_provider(task_text="quick simple typo rename", project_dir=".")
    assert out["provider"] == "kimi"
    assert out["domain_fit"] == "fast_simple"


def test_select_provider_uses_telemetry_and_critic_penalties(monkeypatch):
    monkeypatch.setattr(equalizer, "_probe_provider", lambda _provider: (True, True, "ok"))
    out = equalizer.select_provider(
        task_text="refactor backend API",
        project_dir=".",
        telemetry={
            "providers": {
                "codex": {"latency_ms": 2100, "failure_rate": 0.8},
                "claude": {"latency_ms": 200, "failure_rate": 0.0},
            }
        },
        context_packet={
            "critic_outcomes": {
                "providers": {
                    "codex": {
                        "skeptic": {"verdict": "fail"},
                        "hallucination_auditor": {"verdict": "warn"},
                    }
                }
            }
        },
    )
    assert out["provider"] in {"claude", "gemini", "kimi"}
    assert out["provider"] != "codex"


def test_select_provider_falls_back_to_claude_when_best_unavailable(monkeypatch):
    def _fake_probe(provider: str):
        if provider == "gemini":
            return False, False, "down"
        return True, True, "ok"

    monkeypatch.setattr(equalizer, "_probe_provider", _fake_probe)
    out = equalizer.select_provider(task_text="responsive ui design", project_dir=".")
    assert out["provider"] in {"claude", "codex", "kimi"}
    assert set(out.keys()) == {"provider", "reason", "cost_tier", "domain_fit"}
