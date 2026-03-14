from __future__ import annotations

from pathlib import Path
import zipfile

from runtime.contract_compiler import check_package_parity
from runtime.release_surfaces import get_package_parity_surfaces


def _seed_surface_layout(root: Path) -> list[str]:
    surfaces = get_package_parity_surfaces()
    for surface in surfaces:
        source_skill = root / ".agents" / "skills" / "omg" / surface / "SKILL.md"
        source_skill.parent.mkdir(parents=True, exist_ok=True)
        source_skill.write_text(f"# {surface}\n", encoding="utf-8")

        dist_skill = root / "dist" / "public" / "bundle" / ".agents" / "skills" / "omg" / surface / "SKILL.md"
        dist_skill.parent.mkdir(parents=True, exist_ok=True)
        dist_skill.write_text(f"# {surface}\n", encoding="utf-8")

        release_skill = (
            root
            / "artifacts"
            / "release"
            / "dist"
            / "public"
            / "bundle"
            / ".agents"
            / "skills"
            / "omg"
            / surface
            / "SKILL.md"
        )
        release_skill.parent.mkdir(parents=True, exist_ok=True)
        release_skill.write_text(f"# {surface}\n", encoding="utf-8")

    wheel_path = root / "dist" / "fixture-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, mode="w") as archive:
        for surface in surfaces:
            archive.writestr(f"pkg/.agents/skills/omg/{surface}/SKILL.md", f"# {surface}\n")

    return surfaces


def test_check_package_parity_passes_when_all_required_surfaces_exist(tmp_path: Path) -> None:
    surfaces = _seed_surface_layout(tmp_path)

    result = check_package_parity(tmp_path)

    assert result["status"] == "ok"
    assert result["required_surfaces"] == surfaces
    assert result["machine_blockers"] == []
    assert result["blockers"] == []


def test_check_package_parity_reports_missing_surface_with_machine_blocker(tmp_path: Path) -> None:
    _ = _seed_surface_layout(tmp_path)
    missing_surface = "hash-edit"
    missing_release_path = (
        tmp_path
        / "artifacts"
        / "release"
        / "dist"
        / "public"
        / "bundle"
        / ".agents"
        / "skills"
        / "omg"
        / missing_surface
        / "SKILL.md"
    )
    missing_release_path.unlink()

    result = check_package_parity(tmp_path)

    assert result["status"] == "error"
    assert any("surface=hash-edit" in blocker for blocker in result["blockers"])
    assert any(
        isinstance(blocker, dict)
        and blocker.get("kind") == "package_parity_missing"
        and blocker.get("location") == "release"
        and blocker.get("surface") == "hash-edit"
        for blocker in result["machine_blockers"]
    )
