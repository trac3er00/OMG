from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codex_skill_pack_exists_for_production_contract() -> None:
    skill_dir = ROOT / ".agents" / "skills" / "omg" / "control-plane"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "openai.yaml").exists()


def test_codex_skill_pack_declares_explicit_invocation_policy() -> None:
    openai_yaml = (ROOT / ".agents" / "skills" / "omg" / "control-plane" / "openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in openai_yaml
    assert "omg-control" in openai_yaml
