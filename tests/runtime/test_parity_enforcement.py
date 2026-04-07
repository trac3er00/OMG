from __future__ import annotations

from runtime.prompt_compiler import (
    ProviderCorrection,
    auto_correct_template,
    enforce_parity,
)


TEMPLATE_WITH_HINTS = (
    "You are a helpful assistant. Please explain step by step "
    "how to analyze the output and generate a summary."
)


class TestProviderCorrection:
    def test_apply_replaces_phrases(self):
        correction = ProviderCorrection(
            provider="claude", original_template="You are X"
        )
        correction.add_correction("You are", "As an AI,")
        result = correction.apply()

        assert result == "As an AI, X"
        assert correction.applied is True

    def test_apply_without_corrections_returns_original(self):
        correction = ProviderCorrection(
            provider="codex", original_template="hello world"
        )
        result = correction.apply()

        assert result == "hello world"
        assert correction.applied is True
        assert correction.corrections == []

    def test_to_dict_structure(self):
        correction = ProviderCorrection(provider="gemini", original_template="test")
        correction.add_correction("a", "b")
        d = correction.to_dict()

        assert d["provider"] == "gemini"
        assert d["corrections_count"] == 1
        assert d["applied"] is False
        assert d["corrections"] == [{"from": "a", "to": "b"}]

    def test_original_template_preserved_after_apply(self):
        original = "You are a helpful assistant."
        correction = ProviderCorrection(provider="claude", original_template=original)
        correction.add_correction("You are", "As an AI,")
        correction.apply()

        assert correction.original_template == original


class TestAutoCorrectTemplate:
    def test_parity_enforcement_below_threshold(self):
        # given: template with parity 0.6 on codex
        # when: auto_correct_template is called
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="codex", parity_score=0.6
        )
        # then: corrections are applied for codex hints
        assert len(correction.corrections) > 0
        corrected = correction.apply()
        assert "describe" in corrected
        assert "review" in corrected

    def test_no_correction_when_above_threshold(self):
        # given: parity score 0.9 >= threshold 0.8
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="codex", parity_score=0.9
        )
        # then: no corrections needed
        assert len(correction.corrections) == 0

    def test_no_correction_at_exact_threshold(self):
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="codex", parity_score=0.8
        )
        assert len(correction.corrections) == 0

    def test_original_unchanged_after_correction(self):
        original = TEMPLATE_WITH_HINTS
        correction = auto_correct_template(
            original, provider="gemini", parity_score=0.5
        )
        correction.apply()

        assert correction.original_template == original

    def test_claude_specific_corrections(self):
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="claude", parity_score=0.5
        )
        corrected = correction.apply()
        assert "As an AI assistant," in corrected
        assert "You are" not in corrected

    def test_gemini_specific_corrections(self):
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="gemini", parity_score=0.5
        )
        corrected = correction.apply()
        assert "systematically" in corrected
        assert "step by step" not in corrected

    def test_kimi_specific_corrections(self):
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="kimi", parity_score=0.5
        )
        corrected = correction.apply()
        assert "result" in corrected
        assert "create" in corrected

    def test_unknown_provider_no_corrections(self):
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="unknown_provider", parity_score=0.3
        )
        assert len(correction.corrections) == 0

    def test_custom_threshold(self):
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="codex", parity_score=0.85, threshold=0.9
        )
        assert len(correction.corrections) > 0

    def test_corrected_template_achieves_parity(self):
        # given: template with low parity on codex
        correction = auto_correct_template(
            TEMPLATE_WITH_HINTS, provider="codex", parity_score=0.6
        )
        corrected = correction.apply()
        # then: corrected template differs from original (corrections applied)
        assert corrected != TEMPLATE_WITH_HINTS
        assert correction.applied is True


class TestEnforceParity:
    def test_returns_corrections_for_below_threshold_only(self):
        scores = {"claude": 0.9, "codex": 0.6, "gemini": 0.5}
        corrections = enforce_parity("tmpl-1", TEMPLATE_WITH_HINTS, scores)

        assert "claude" not in corrections
        assert "codex" in corrections
        assert "gemini" in corrections

    def test_empty_when_all_above_threshold(self):
        scores = {"claude": 0.9, "codex": 0.85, "gemini": 0.95}
        corrections = enforce_parity("tmpl-1", TEMPLATE_WITH_HINTS, scores)

        assert corrections == {}

    def test_all_providers_below_threshold(self):
        scores = {"claude": 0.5, "codex": 0.6, "gemini": 0.3, "kimi": 0.4}
        corrections = enforce_parity("tmpl-1", TEMPLATE_WITH_HINTS, scores)

        assert len(corrections) == 4

    def test_corrections_are_transparent_logged(self):
        scores = {"codex": 0.6}
        corrections = enforce_parity("tmpl-1", TEMPLATE_WITH_HINTS, scores)

        info = corrections["codex"].to_dict()
        assert info["provider"] == "codex"
        assert info["corrections_count"] > 0
        assert isinstance(info["corrections"], list)
        assert all("from" in c and "to" in c for c in info["corrections"])

    def test_custom_threshold(self):
        scores = {"codex": 0.85}
        corrections = enforce_parity(
            "tmpl-1", TEMPLATE_WITH_HINTS, scores, threshold=0.9
        )
        assert "codex" in corrections
