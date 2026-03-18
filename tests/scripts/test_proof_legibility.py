"""Tests that proof documentation is operator-legible, not just machine-legible.

Prevents the recurring issue where docs/proof.md centers artifact paths and
JSON field names without explaining what pass/fail means for operators.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestProofLegibility:
    """docs/proof.md must have human-readable content alongside machine artifacts."""

    def _read_proof_doc(self) -> str:
        return (REPO_ROOT / "docs" / "proof.md").read_text(encoding="utf-8")

    def test_proof_doc_has_human_readable_verdict_section(self) -> None:
        """docs/proof.md must have a section explaining how to read proof output."""
        content = self._read_proof_doc()
        has_how_to = "How to Read" in content
        has_verdict = "Quick Verdict" in content
        assert has_how_to or has_verdict, (
            "docs/proof.md must contain a human-readable verdict section "
            "(e.g. 'How to Read Your Proof' or 'Quick Verdict')"
        )

    def test_proof_doc_has_common_commands(self) -> None:
        """docs/proof.md must have a quick-reference for common proof commands."""
        content = self._read_proof_doc()
        assert "omg proof" in content, "docs/proof.md must reference 'omg proof'"
        assert "omg blocked" in content, "docs/proof.md must reference 'omg blocked'"
        assert "omg explain run --run-id <id>" in content, (
            "docs/proof.md must show the real explain-run syntax"
        )
        assert "omg explain run <id>" not in content, (
            "docs/proof.md must not advertise unsupported positional explain-run syntax"
        )

    def test_proof_doc_explains_pass_and_fail(self) -> None:
        """docs/proof.md must explain what pass and fail mean in plain language."""
        content = self._read_proof_doc()
        lower = content.lower()
        assert "pass" in lower and "means" in lower, (
            "docs/proof.md must explain what 'pass' means"
        )
        assert "fail" in lower and "means" in lower, (
            "docs/proof.md must explain what 'fail' means"
        )

    def test_proof_doc_not_artifact_paths_only(self) -> None:
        """docs/proof.md must not be exclusively artifact paths without human context."""
        content = self._read_proof_doc()
        lines = [
            line.strip()
            for line in content.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        if not lines:
            return
        artifact_lines = [
            line for line in lines if ".omg/" in line or "`.omg/" in line
        ]
        human_lines = [
            line for line in lines if ".omg/" not in line
        ]
        ratio = len(human_lines) / len(lines)
        assert ratio > 0.3, (
            f"docs/proof.md is {100 * (1 - ratio):.0f}% machine artifact paths "
            "-- needs more human-readable content"
        )
