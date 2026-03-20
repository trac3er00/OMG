"""Tests that the proof docs describe the platform-level certification story."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestProofStory:
    """Proof docs should frame Music OMR as one certification lane, not the whole system."""

    def test_proof_doc_introduces_certification_lanes_before_music_omr(self) -> None:
        path = REPO_ROOT / "docs" / "proof.md"
        content = path.read_text(encoding="utf-8")
        lanes_idx = content.find("## Certification Lanes")
        music_idx = content.find("## Permanent Music OMR Daily Gate")
        assert lanes_idx >= 0, "proof.md must introduce certification lanes"
        assert music_idx >= 0, "proof.md must keep the Music OMR lane"
        assert lanes_idx < music_idx, "Certification lanes must frame Music OMR, not follow it"

    def test_proof_doc_lists_platform_lanes(self) -> None:
        path = REPO_ROOT / "docs" / "proof.md"
        content = path.read_text(encoding="utf-8")
        for lane in (
            "Lane 1",
            "install/apply correctness",
            "uninstall cleanliness",
            "host parity",
            "trust-chain verification",
            "proof-surface integrity",
        ):
            assert lane in content, f"Missing certification lane reference: {lane}"

    def test_readme_frames_music_omr_as_certification_lane_1(self) -> None:
        path = REPO_ROOT / "README.md"
        content = path.read_text(encoding="utf-8")
        proof_idx = content.find("## Proof")
        assert proof_idx >= 0, "README must have a Proof section"
        next_section = content.find("\n## ", proof_idx + 1)
        section = content[proof_idx : next_section if next_section > 0 else len(content)]
        assert "Certification Lane 1" in section
        assert "Flagship testbed" not in section

    def test_proof_docs_keep_music_omr_as_flagship_gate(self) -> None:
        path = REPO_ROOT / "docs" / "proof.md"
        content = path.read_text(encoding="utf-8")
        assert "Music OMR" in content and "flagship" in content.lower()
        assert "Lane 1" in content and "flagship" in content.lower()

    def test_readme_keeps_music_omr_as_flagship_gate(self) -> None:
        path = REPO_ROOT / "README.md"
        content = path.read_text(encoding="utf-8")
        proof_idx = content.find("## Proof")
        assert proof_idx >= 0, "README must have a Proof section"
        next_section = content.find("\n## ", proof_idx + 1)
        section = content[proof_idx : next_section if next_section > 0 else len(content)]
        assert "flagship" in section.lower()
