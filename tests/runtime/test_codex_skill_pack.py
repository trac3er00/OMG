from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "codex-skills"


def test_codex_skill_pack_contains_expected_skill_directories():
    expected = {
        "omg-orchestrator",
        "omg-provider-interop",
        "omg-verified-delivery",
    }
    assert SKILLS_ROOT.exists()
    assert expected.issubset({path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()})


def test_each_codex_skill_has_skill_md_and_openai_metadata():
    for skill_name in ("omg-orchestrator", "omg-provider-interop", "omg-verified-delivery"):
        skill_dir = SKILLS_ROOT / skill_name
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "agents" / "openai.yaml").exists()
