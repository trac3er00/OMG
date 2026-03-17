"""Tests for runtime.release_surface_compiler — public API contract tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.release_surface_compiler import compile_release_surfaces


_MINIMAL_OMG_PY = '''\
import argparse

def build_parser():
    parser = argparse.ArgumentParser(prog="omg")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("ship", help="Idea-to-PR flow")
    sub.add_parser("fix", help="Issue-driven fix flow")
    sub.add_parser("setup", help="Setup flow")
    return parser
'''

_INSTALL_GUIDE_NAMES = (
    "claude-code",
    "codex",
    "gemini",
    "kimi",
    "opencode",
    "github-app",
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text(
        "# OMG\n\nIntro text.\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 2.2.7 - 2026-03-15\n\n- initial\n",
        encoding="utf-8",
    )
    install_dir = tmp_path / "docs" / "install"
    install_dir.mkdir(parents=True, exist_ok=True)
    for name in _INSTALL_GUIDE_NAMES:
        (install_dir / f"{name}.md").write_text(
            f"# Install {name}\n\nInstructions.\n",
            encoding="utf-8",
        )
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "omg.py").write_text(_MINIMAL_OMG_PY, encoding="utf-8")
    return tmp_path


def test_manifest_emitted_to_both_channels(project: Path) -> None:
    result = compile_release_surfaces(project)

    assert result["status"] == "ok"

    pub = project / "dist" / "public" / "release-surface.json"
    ent = project / "dist" / "enterprise" / "release-surface.json"
    assert pub.exists()
    assert ent.exists()

    pub_data = json.loads(pub.read_text())
    ent_data = json.loads(ent.read_text())
    assert "surfaces" in pub_data
    assert "surfaces" in ent_data
    assert pub_data["version"] is not None

    assert "dist/public/release-surface.json" in result["artifacts"]
    assert "dist/enterprise/release-surface.json" in result["artifacts"]


def test_readme_quickstart_marker_inserted(project: Path) -> None:
    compile_release_surfaces(project)

    content = (project / "README.md").read_text()
    assert "<!-- OMG:GENERATED:quickstart -->" in content
    assert "<!-- /OMG:GENERATED:quickstart -->" in content


def test_readme_markers_idempotent(project: Path) -> None:
    compile_release_surfaces(project)
    first = (project / "README.md").read_text()

    compile_release_surfaces(project)
    second = (project / "README.md").read_text()

    assert second.count("<!-- OMG:GENERATED:quickstart -->") == 1
    assert second.count("<!-- /OMG:GENERATED:quickstart -->") == 1
    assert first == second


def test_install_guides_get_fast_path(project: Path) -> None:
    compile_release_surfaces(project)

    for name in _INSTALL_GUIDE_NAMES:
        guide = project / "docs" / "install" / f"{name}.md"
        content = guide.read_text()
        assert "<!-- OMG:GENERATED:install-fast-path -->" in content, (
            f"open marker missing in {name}"
        )
        assert "<!-- /OMG:GENERATED:install-fast-path -->" in content, (
            f"close marker missing in {name}"
        )


def test_install_guide_fast_path_idempotent(project: Path) -> None:
    compile_release_surfaces(project)
    compile_release_surfaces(project)

    for name in _INSTALL_GUIDE_NAMES:
        content = (project / "docs" / "install" / f"{name}.md").read_text()
        assert content.count("<!-- OMG:GENERATED:install-fast-path -->") == 1, (
            f"duplicate marker in {name}"
        )


def test_command_surface_doc_created(project: Path) -> None:
    result = compile_release_surfaces(project)

    cmd_surface = project / "docs" / "command-surface.md"
    assert cmd_surface.exists()
    content = cmd_surface.read_text()
    assert "Command Surface" in content
    assert "omg ship" in content
    assert "docs/command-surface.md" in result["artifacts"]


def test_changelog_marker_inserted(project: Path) -> None:
    compile_release_surfaces(project)

    content = (project / "CHANGELOG.md").read_text()
    assert "<!-- OMG:GENERATED:changelog-v2.2.7 -->" in content
    assert "<!-- /OMG:GENERATED:changelog-v2.2.7 -->" in content


def test_changelog_marker_near_top(project: Path) -> None:
    compile_release_surfaces(project)

    content = (project / "CHANGELOG.md").read_text()
    heading_pos = content.find("# Changelog")
    marker_pos = content.find("<!-- OMG:GENERATED:changelog-v2.2.7 -->")
    assert 0 <= heading_pos < marker_pos


def test_release_notes_artifact_created(project: Path) -> None:
    result = compile_release_surfaces(project)

    notes = project / "artifacts" / "release" / "release-notes-v2.2.7.md"
    assert notes.exists()
    content = notes.read_text()
    assert "2.2.7" in content
    assert "artifacts/release/release-notes-v2.2.7.md" in result["artifacts"]


def test_return_structure(project: Path) -> None:
    result = compile_release_surfaces(project)

    assert result["status"] == "ok"
    assert isinstance(result["artifacts"], list)
    assert isinstance(result["sections_updated"], list)
    assert len(result["artifacts"]) > 0
    assert len(result["sections_updated"]) > 0
