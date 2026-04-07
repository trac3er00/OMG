"""Cross-provider parity measurement for prompt templates."""

from __future__ import annotations

import json

import pytest

from runtime.prompt_compiler import (
    ParityScore,
    compute_structural_similarity,
    generate_parity_report,
    measure_template_parity,
)

REFERENCE_PROMPTS: dict[str, dict[str, str]] = {
    "bugfix-reproduce-first": {
        "claude": (
            "# Bug Analysis\n"
            "## Steps to Reproduce\n"
            "1. Read the relevant code paths\n"
            "2. Write a failing test that triggers the bug\n"
            "3. Fix the root cause\n"
            "## Verification\n"
            "Run the test suite to confirm the fix."
        ),
        "gpt4": (
            "# Bug Analysis\n"
            "## Reproduction Steps\n"
            "1. Examine the code paths involved\n"
            "2. Create a failing test case\n"
            "3. Apply the fix\n"
            "## Verify\n"
            "Run tests to confirm resolution."
        ),
        "gemini": (
            "# Bug Report\n"
            "## Reproduce\n"
            "1. Read code to understand the flow\n"
            "2. Write a test that fails\n"
            "3. Fix the issue\n"
            "## Check\n"
            "Execute test suite for verification."
        ),
    },
    "feature-plan-first": {
        "claude": (
            "# Feature Plan\n"
            "## Interface Design\n"
            "Define public API surface.\n"
            "## Implementation\n"
            "Implement incrementally with tests.\n"
            "## Review\n"
            "Verify all tests pass."
        ),
        "gpt4": (
            "# Feature Plan\n"
            "## API Design\n"
            "Define the interface.\n"
            "## Build\n"
            "Implement step by step.\n"
            "## Validate\n"
            "Run full test suite."
        ),
        "gemini": (
            "# Feature Plan\n"
            "## Design\n"
            "Plan the interface.\n"
            "## Code\n"
            "Build incrementally.\n"
            "## Test\n"
            "Confirm all tests pass."
        ),
    },
    "divergent-template": {
        "claude": (
            "# Security Audit\n"
            "## Threat Model\n"
            "Identify attack surfaces and threat actors.\n"
            "## OWASP Check\n"
            "Review against OWASP Top 10.\n"
            "## Remediation\n"
            "Fix all critical vulnerabilities before release."
        ),
        "gpt4": "Check for bugs. Fix them.",
        "gemini": "Look at the code. Make changes.",
    },
}


class TestParityMeasurement:
    def test_parity_scores_computed_for_reference_prompts(self) -> None:
        scores = []
        for template_id, outputs in REFERENCE_PROMPTS.items():
            score = measure_template_parity(template_id, outputs)
            scores.append(score)

        assert len(scores) == len(REFERENCE_PROMPTS)
        for score in scores:
            assert score.template_id in REFERENCE_PROMPTS
            assert len(score.scores) > 0

    def test_score_range(self) -> None:
        for template_id, outputs in REFERENCE_PROMPTS.items():
            score = measure_template_parity(template_id, outputs)
            for provider, value in score.scores.items():
                assert isinstance(value, float), f"{provider} score is not float"
                assert 0.0 <= value <= 1.0, f"{provider} score {value} out of range"
            assert isinstance(score.average_score, float)
            assert 0.0 <= score.average_score <= 1.0

    def test_low_parity_identified(self) -> None:
        scores = [
            measure_template_parity(tid, outputs)
            for tid, outputs in REFERENCE_PROMPTS.items()
        ]
        report = generate_parity_report(scores)

        assert report["low_parity_count"] >= 1
        assert "divergent-template" in report["low_parity_templates"]

    def test_identical_outputs(self) -> None:
        text = "# Plan\n## Step 1\nDo the thing.\n## Step 2\nVerify."
        outputs = {"claude": text, "gpt4": text, "gemini": text}
        score = measure_template_parity("identical-test", outputs)

        assert score.scores["claude"] == 1.0
        for provider in ["gpt4", "gemini"]:
            assert score.scores[provider] == 1.0
        assert score.average_score == 1.0
        assert not score.is_low_parity

    def test_different_outputs(self) -> None:
        outputs = {
            "claude": (
                "# Security Audit\n"
                "## Threat Model\n"
                "Identify attack surfaces and threat actors.\n"
                "## OWASP Check\n"
                "Review against OWASP Top 10.\n"
                "## Remediation Plan\n"
                "Fix all critical vulnerabilities before release."
            ),
            "gpt4": "Check for bugs.",
            "gemini": "Look at the code.",
        }
        score = measure_template_parity("different-test", outputs)

        assert score.average_score < 0.8
        assert score.is_low_parity


class TestParityScore:
    def test_empty_scores(self) -> None:
        ps = ParityScore("empty")
        assert ps.average_score == 0.0
        assert ps.is_low_parity

    def test_to_dict(self) -> None:
        ps = ParityScore("t1")
        ps.add_score("claude", 0.95)
        ps.add_score("gpt4", 0.85)
        d = ps.to_dict()
        assert d["template_id"] == "t1"
        assert d["scores"] == {"claude": 0.95, "gpt4": 0.85}
        assert d["average"] == pytest.approx(0.9)
        assert d["low_parity"] is False

    def test_single_provider(self) -> None:
        score = measure_template_parity("single", {"claude": "any output"})
        assert score.scores["claude"] == 1.0
        assert score.average_score == 1.0


class TestStructuralSimilarity:
    def test_identical_strings(self) -> None:
        assert compute_structural_similarity("hello world", "hello world") == 1.0

    def test_empty_strings(self) -> None:
        assert compute_structural_similarity("", "") == 1.0

    def test_completely_different(self) -> None:
        a = "alpha beta gamma delta epsilon"
        b = "one two three four five six seven eight nine ten"
        sim = compute_structural_similarity(a, b)
        assert sim < 0.5

    def test_symmetry_approximately(self) -> None:
        a = "# Header\nSome content here with words"
        b = "# Header\nDifferent content with other words"
        sim_ab = compute_structural_similarity(a, b)
        sim_ba = compute_structural_similarity(b, a)
        assert sim_ab == pytest.approx(sim_ba, abs=0.01)


class TestParityReport:
    def test_report_structure(self) -> None:
        scores = [
            measure_template_parity(tid, outputs)
            for tid, outputs in REFERENCE_PROMPTS.items()
        ]
        report = generate_parity_report(scores)

        assert "total_templates" in report
        assert "low_parity_count" in report
        assert "templates" in report
        assert "low_parity_templates" in report
        assert report["total_templates"] == len(REFERENCE_PROMPTS)

    def test_report_serializable(self) -> None:
        scores = [
            measure_template_parity(tid, outputs)
            for tid, outputs in REFERENCE_PROMPTS.items()
        ]
        report = generate_parity_report(scores)
        serialized = json.dumps(report)
        assert isinstance(serialized, str)
        roundtrip = json.loads(serialized)
        assert roundtrip["total_templates"] == report["total_templates"]

    def test_empty_report(self) -> None:
        report = generate_parity_report([])
        assert report["total_templates"] == 0
        assert report["low_parity_count"] == 0
        assert report["templates"] == []
        assert report["low_parity_templates"] == []
