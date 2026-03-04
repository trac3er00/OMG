"""E2E-style coverage guard for legacy skill compatibility."""
from __future__ import annotations

from pathlib import Path

from runtime.compat import build_compat_gap_report, dispatch_compat_skill, list_compat_skills


ROOT = Path(__file__).resolve().parents[2]


def test_compat_skill_count_has_standalone_coverage():
    compat_skills = list_compat_skills()
    assert len(compat_skills) >= 30
    assert "omg-teams" in compat_skills
    assert "ccg" in compat_skills


def test_compat_skill_set_stays_large_enough_for_legacy_coverage():
    compat_skills = set(list_compat_skills())
    assert len(compat_skills) >= 30


def test_all_legacy_skills_run_in_standalone_mode(tmp_path: Path):
    for skill in list_compat_skills():
        result = dispatch_compat_skill(
            skill=skill,
            problem=f"standalone coverage {skill}",
            project_dir=str(tmp_path),
        )
        assert result["schema"] == "OmgCompatResult"
        assert result["status"] == "ok", f"{skill} failed with {result}"


def test_gap_report_is_emitted(tmp_path: Path):
    report = build_compat_gap_report(str(tmp_path))
    assert report["schema"] == "OmgCompatGapReport"
    assert report["total_skills"] >= 30
    assert report["maturity_counts"].get("native", 0) == report["total_skills"]
    assert report["maturity_counts"].get("bridge", 0) == 0
    assert (tmp_path / ".omg" / "evidence" / "omg-compat-gap.json").exists()
    assert (tmp_path / ".omg" / "evidence" / "compat-gap.json").exists()
