from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "codex-skills"
EXPECTED_CODEX_SKILLS = {
    "omg-codex-workbench",
    "omg-orchestrator",
    "omg-provider-interop",
    "omg-verified-delivery",
    "omg-deep-execution",
    "omg-runtime-triage",
    "omg-review-gate",
    "omg-session-continuity",
    "omg-release-readiness",
}


def test_codex_skill_pack_contains_expected_skill_directories():
    assert SKILLS_ROOT.exists()
    assert EXPECTED_CODEX_SKILLS.issubset({path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()})


def test_each_codex_skill_has_skill_md_and_openai_metadata():
    for skill_name in EXPECTED_CODEX_SKILLS:
        skill_dir = SKILLS_ROOT / skill_name
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "agents" / "openai.yaml").exists()


def test_codex_workbench_skill_contains_hud_reference():
    content = (SKILLS_ROOT / "omg-codex-workbench" / "SKILL.md").read_text(encoding="utf-8")
    assert "omg-codex-hud" in content
    assert "Codex-only" in content
