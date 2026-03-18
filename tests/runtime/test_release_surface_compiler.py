"""Tests for runtime.release_surface_compiler — public API contract tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.adoption import CANONICAL_VERSION
from runtime.release_surface_compiler import (
    compile_release_surfaces,
    _compile_release_text,
    _quickstart_content,
    _install_fast_path_content,
    _proof_content,
    _command_surface_snippet,
    _install_intro_content,
    _why_omg_content,
    _proof_quickstart_content,
    _quick_reference_hosts_content,
    _verification_index_targets_content,
)


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
    proof_dir = tmp_path / "docs"
    (proof_dir / "proof.md").write_text(
        "# OMG Proof Surface\n\n## Verification Status\n\nDetails.\n",
        encoding="utf-8",
    )
    (tmp_path / "QUICK-REFERENCE.md").write_text(
        "<!-- GENERATED: DO NOT EDIT MANUALLY -->\n# OMG Quick Reference\n\nContent.\n",
        encoding="utf-8",
    )
    (tmp_path / "INSTALL-VERIFICATION-INDEX.md").write_text(
        "<!-- GENERATED: DO NOT EDIT MANUALLY -->\n# OMG Install Verification\n\nContent.\n",
        encoding="utf-8",
    )
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


def test_registry_includes_release_body_surfaces() -> None:
    from runtime.release_surface_registry import get_public_surfaces

    surfaces = get_public_surfaces()
    ids = {s["id"] for s in surfaces}
    assert "github_release_body_artifact" in ids
    assert "tag_body_artifact" in ids


def test_registry_includes_proof_section_marker() -> None:
    from runtime.release_surface_registry import get_generated_section_markers

    markers = get_generated_section_markers()
    assert "proof_generated_section" in markers


def test_promoted_commands_available_to_compiler() -> None:
    from runtime.release_surface_registry import PROMOTED_PUBLIC_COMMANDS

    assert isinstance(PROMOTED_PUBLIC_COMMANDS, list)
    assert len(PROMOTED_PUBLIC_COMMANDS) > 0
    for cmd in PROMOTED_PUBLIC_COMMANDS:
        assert "crazy" not in cmd.lower()


def test_compile_release_text_produces_canonical_content() -> None:
    text = _compile_release_text(CANONICAL_VERSION)
    assert f"v{CANONICAL_VERSION}" in text
    assert "Canonical release surface compilation" in text
    assert "Dual-channel" in text
    assert "Idempotent generated-section markers" in text


def test_release_text_shared_across_all_outputs(project: Path) -> None:
    compile_release_surfaces(project)
    canonical = _compile_release_text(CANONICAL_VERSION)

    changelog = (project / "CHANGELOG.md").read_text(encoding="utf-8")
    assert canonical in changelog, "canonical text missing from CHANGELOG.md generated block"

    notes = (project / "artifacts" / "release" / f"release-notes-v{CANONICAL_VERSION}.md").read_text(encoding="utf-8")
    assert canonical in notes, "canonical text missing from release notes artifact"

    body = (project / "artifacts" / "release" / f"release-body-v{CANONICAL_VERSION}.md").read_text(encoding="utf-8")
    assert canonical in body, "canonical text missing from release body artifact"

    tag = (project / "artifacts" / "release" / f"tag-body-v{CANONICAL_VERSION}.md").read_text(encoding="utf-8")
    assert canonical in tag, "canonical text missing from tag body artifact"


def test_release_body_artifact_created(project: Path) -> None:
    result = compile_release_surfaces(project)
    body = project / "artifacts" / "release" / f"release-body-v{CANONICAL_VERSION}.md"
    assert body.exists()
    content = body.read_text(encoding="utf-8")
    assert f"v{CANONICAL_VERSION}" in content
    assert f"artifacts/release/release-body-v{CANONICAL_VERSION}.md" in result["artifacts"]


def test_tag_body_artifact_created(project: Path) -> None:
    result = compile_release_surfaces(project)
    tag = project / "artifacts" / "release" / f"tag-body-v{CANONICAL_VERSION}.md"
    assert tag.exists()
    content = tag.read_text(encoding="utf-8")
    assert f"v{CANONICAL_VERSION}" in content
    assert f"artifacts/release/tag-body-v{CANONICAL_VERSION}.md" in result["artifacts"]


def test_check_only_returns_ok_when_fresh(project: Path) -> None:
    compile_release_surfaces(project)
    result = compile_release_surfaces(project, check_only=True)
    assert result["status"] == "ok"
    assert result["drift"] == []


def test_check_only_detects_changelog_marker_tampering(project: Path) -> None:
    compile_release_surfaces(project)

    cl = project / "CHANGELOG.md"
    content = cl.read_text(encoding="utf-8")
    content = content.replace("Canonical release surface compilation", "TAMPERED CONTENT")
    cl.write_text(content, encoding="utf-8")

    result = compile_release_surfaces(project, check_only=True)
    assert result["status"] == "drift"
    assert len(result["drift"]) > 0
    drift_surfaces = [d["surface"] for d in result["drift"]]
    assert "changelog_current" in drift_surfaces


def test_check_only_detects_readme_marker_tampering(project: Path) -> None:
    compile_release_surfaces(project)

    readme = project / "README.md"
    content = readme.read_text(encoding="utf-8")
    content = content.replace("omg install --plan", "TAMPERED INSTALL CMD")
    readme.write_text(content, encoding="utf-8")

    result = compile_release_surfaces(project, check_only=True)
    assert result["status"] == "drift"
    drift_surfaces = [d["surface"] for d in result["drift"]]
    assert "readme_quickstart" in drift_surfaces


def test_check_only_does_not_write_files(project: Path) -> None:
    compile_release_surfaces(project)

    cl = project / "CHANGELOG.md"
    original = cl.read_text(encoding="utf-8")
    tampered = original.replace("Canonical release surface compilation", "TAMPERED")
    cl.write_text(tampered, encoding="utf-8")

    compile_release_surfaces(project, check_only=True)
    assert cl.read_text(encoding="utf-8") == tampered, "check_only must not overwrite files"


def test_check_only_detects_missing_artifact(project: Path) -> None:
    compile_release_surfaces(project)

    body = project / "artifacts" / "release" / f"release-body-v{CANONICAL_VERSION}.md"
    body.unlink()

    result = compile_release_surfaces(project, check_only=True)
    assert result["status"] == "drift"
    drift_surfaces = [d["surface"] for d in result["drift"]]
    assert "github_release_body" in drift_surfaces


class TestQuickstartContent:

    def test_quickstart_shows_omg_install_plan(self) -> None:
        content = _quickstart_content()
        assert "omg install --plan" in content

    def test_quickstart_shows_omg_install_apply(self) -> None:
        content = _quickstart_content()
        assert "omg install --apply" in content

    def test_quickstart_leads_with_install_step(self) -> None:
        content = _quickstart_content()
        lines = content.split("\n")
        first_code_block = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            if line.strip().startswith("```") and in_block:
                break
            if in_block:
                first_code_block.append(line)
        first_block_text = "\n".join(first_code_block)
        assert first_block_text.startswith("npm install -g @trac3er/oh-my-god"), (
            "quickstart should start by installing the omg binary"
        )

    def test_quickstart_crazy_only_in_footnote(self) -> None:
        content = _quickstart_content()
        lines = content.split("\n")
        for line in lines:
            if "/OMG:crazy" in line or "OMG:crazy" in line:
                lowered = line.lower()
                assert any(
                    w in lowered for w in ("compat", "footnote", "legacy", "alias", ">")
                ), f"/OMG:crazy must appear only in footnote context, found in: {line!r}"

    def test_quickstart_in_readme_after_compile(self, project: Path) -> None:
        compile_release_surfaces(project)
        content = (project / "README.md").read_text()
        assert "omg install --plan" in content


class TestInstallFastPathContent:

    def test_fast_path_has_node_prerequisite(self) -> None:
        content = _install_fast_path_content()
        assert "Node" in content and "18" in content, "Node >=18 prerequisite missing"

    def test_fast_path_shows_omg_install_plan(self) -> None:
        content = _install_fast_path_content()
        assert "omg install --plan" in content

    def test_fast_path_shows_omg_install_apply(self) -> None:
        content = _install_fast_path_content()
        assert "omg install --apply" in content

    def test_fast_path_in_install_guides(self, project: Path) -> None:
        compile_release_surfaces(project)
        for name in _INSTALL_GUIDE_NAMES:
            content = (project / "docs" / "install" / f"{name}.md").read_text()
            assert "Node" in content and "18" in content, (
                f"Node >=18 prerequisite missing from {name}"
            )


class TestProofContent:

    def test_proof_shows_proof_open_html(self) -> None:
        content = _proof_content()
        assert "omg proof open --html" in content

    def test_proof_shows_blocked_last(self) -> None:
        content = _proof_content()
        assert "omg blocked --last" in content

    def test_proof_shows_explain_run(self) -> None:
        content = _proof_content()
        assert "omg explain run" in content

    def test_proof_shows_budget_simulate(self) -> None:
        content = _proof_content()
        assert "omg budget simulate --enforce" in content

    def test_proof_human_commands_before_artifact_paths(self) -> None:
        content = _proof_content()
        cmd_pos = content.find("omg proof open --html")
        artifact_pos = content.find(".omg/evidence")
        if artifact_pos >= 0:
            assert cmd_pos < artifact_pos, "Human commands must come before artifact paths"

    def test_proof_section_in_readme(self, project: Path) -> None:
        compile_release_surfaces(project)
        content = (project / "README.md").read_text()
        assert "<!-- OMG:GENERATED:proof -->" in content
        assert "omg proof open --html" in content


class TestCommandSurfaceSnippet:

    def test_command_surface_uses_promoted_commands(self, project: Path) -> None:
        content = _command_surface_snippet(project)
        assert "omg ship" in content
        assert "omg proof" in content
        assert "omg install --plan" in content

    def test_command_surface_does_not_include_crazy(self, project: Path) -> None:
        content = _command_surface_snippet(project)
        assert "crazy" not in content.lower()

    def test_command_surface_works_without_omg_py(self, project: Path) -> None:
        no_omg = project / "no-omg-dir"
        no_omg.mkdir()
        (no_omg / "README.md").write_text("# test\n")
        content = _command_surface_snippet(no_omg)
        assert "omg ship" in content
        assert "omg proof" in content


class TestInstallIntroContent:

    def test_leads_with_install_step(self) -> None:
        content = _install_intro_content()
        lines = content.split("\n")
        code_lines = [l for l in lines if l.startswith("npm install") or l.startswith("npx ") or l.startswith("omg ")]
        assert code_lines[0].startswith("npm install -g @trac3er/oh-my-god")

    def test_states_npm_install_no_mutations(self) -> None:
        content = _install_intro_content()
        assert "bin linking only" in content
        assert "no mutations" in content.lower()

    def test_states_postinstall_plan_only(self) -> None:
        content = _install_intro_content()
        assert "omg install --plan" in content
        assert "preview" in content.lower()

    def test_does_not_contain_does_two_things(self) -> None:
        content = _install_intro_content()
        assert "does two things" not in content.lower()

    def test_does_not_use_bare_npx_omg(self) -> None:
        content = _install_intro_content()
        assert "npx omg" not in content

    def test_local_without_global_uses_scoped_package(self) -> None:
        content = _install_intro_content()
        assert "@trac3er/oh-my-god" in content

    def test_install_intro_in_readme(self, project: Path) -> None:
        compile_release_surfaces(project)
        content = (project / "README.md").read_text()
        assert "<!-- OMG:GENERATED:install-intro -->" in content
        assert "npm install -g @trac3er/oh-my-god" in content


class TestWhyOmgContent:

    def test_slash_commands_in_footnote_only(self) -> None:
        content = _why_omg_content()
        for line in content.split("\n"):
            if "/OMG:" in line:
                assert line.startswith(">"), f"Slash command not in footnote: {line!r}"

    def test_mentions_opencode(self) -> None:
        content = _why_omg_content()
        assert "OpenCode" in content

    def test_why_omg_in_readme(self, project: Path) -> None:
        compile_release_surfaces(project)
        content = (project / "README.md").read_text()
        assert "<!-- OMG:GENERATED:why-omg -->" in content


class TestProofQuickstartContent:

    def test_leads_with_proof_open(self) -> None:
        content = _proof_quickstart_content()
        lines = content.split("\n")
        code_lines = [l for l in lines if l.startswith("omg ")]
        assert code_lines[0].startswith("omg proof open --html")

    def test_shows_blocked_last(self) -> None:
        content = _proof_quickstart_content()
        assert "omg blocked --last" in content

    def test_proof_quickstart_in_proof_doc(self, project: Path) -> None:
        compile_release_surfaces(project)
        content = (project / "docs" / "proof.md").read_text()
        assert "<!-- OMG:GENERATED:proof-quickstart -->" in content
        assert "omg proof open --html" in content


class TestQuickReferenceHosts:

    def test_includes_opencode(self) -> None:
        content = _quick_reference_hosts_content()
        assert "opencode" in content

    def test_includes_all_canonical_hosts(self) -> None:
        content = _quick_reference_hosts_content()
        for host in ("claude", "codex", "gemini", "kimi"):
            assert host in content

    def test_quick_ref_hosts_in_doc(self, project: Path) -> None:
        compile_release_surfaces(project)
        content = (project / "QUICK-REFERENCE.md").read_text()
        assert "<!-- OMG:GENERATED:quick-reference-hosts -->" in content
        assert "opencode" in content


class TestVerificationIndexTargets:

    def test_includes_opencode(self) -> None:
        content = _verification_index_targets_content()
        assert "OpenCode" in content

    def test_includes_all_canonical_targets(self) -> None:
        content = _verification_index_targets_content()
        for host in ("Claude", "Codex", "Gemini", "Kimi"):
            assert host in content

    def test_verification_index_in_doc(self, project: Path) -> None:
        compile_release_surfaces(project)
        content = (project / "INSTALL-VERIFICATION-INDEX.md").read_text()
        assert "<!-- OMG:GENERATED:verification-index-targets -->" in content
        assert "OpenCode" in content


class TestDocsKillGuards:
    """Ensure banned language never returns in documentation."""

    def test_does_two_things_language_eliminated(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for md in root.rglob("*.md"):
            rel = md.relative_to(root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if "node_modules" in str(rel):
                continue
            content = md.read_text(encoding="utf-8")
            assert "does two things" not in content.lower(), (
                f"Banned phrase 'does two things' found in {rel}"
            )

    def test_install_fast_path_states_no_mutations(self) -> None:
        content = _install_fast_path_content()
        assert "no mutations" in content.lower()
        assert "omg install --apply" in content
