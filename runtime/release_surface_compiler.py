from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.adoption import CANONICAL_VERSION
from runtime.release_surface_registry import (
    PUBLIC_SURFACES,
    GENERATED_SECTION_MARKERS,
    get_public_surfaces,
    get_generated_section_markers,
    get_promoted_public_commands,
)


def compile_release_surfaces(
    root: Path,
    *,
    check_only: bool = False,
) -> dict[str, Any]:
    if check_only:
        return _check_release_surfaces(root)

    artifacts: list[str] = []
    sections_updated: list[str] = []
    markers = get_generated_section_markers()
    surfaces = get_public_surfaces()
    timestamp = datetime.now(timezone.utc).isoformat()

    manifest = _build_manifest(surfaces, timestamp)
    for channel in ("public", "enterprise"):
        out = root / "dist" / channel / "release-surface.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        _write_json(out, manifest)
        artifacts.append(str(out.relative_to(root)))

    release_dir = root / "artifacts" / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    notes_path = release_dir / f"release-notes-v{CANONICAL_VERSION}.md"
    notes_path.write_text(_release_notes_content(), encoding="utf-8")
    artifacts.append(str(notes_path.relative_to(root)))

    body_path = release_dir / f"release-body-v{CANONICAL_VERSION}.md"
    body_path.write_text(_release_body_content(), encoding="utf-8")
    artifacts.append(str(body_path.relative_to(root)))

    tag_path = release_dir / f"tag-body-v{CANONICAL_VERSION}.md"
    tag_path.write_text(_tag_body_content(), encoding="utf-8")
    artifacts.append(str(tag_path.relative_to(root)))

    readme = root / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        quickstart_key = _marker_key(markers.get("readme_quickstart", "")) or "quickstart"
        content, updated = _upsert_section(content, quickstart_key, _quickstart_content())
        if updated:
            sections_updated.append("readme_quickstart")
        cmd_key = _marker_key(markers.get("readme_command_surface", "")) or "command-surface"
        content, updated = _upsert_section(content, cmd_key, _command_surface_snippet(root))
        if updated:
            sections_updated.append("readme_command_surface")
        proof_key = _marker_key(markers.get("proof_generated_section", "")) or "proof"
        content, updated = _upsert_section(content, proof_key, _proof_content())
        if updated:
            sections_updated.append("proof_generated_section")
        intro_key = _marker_key(markers.get("install_intro", "")) or "install-intro"
        content, updated = _upsert_section(content, intro_key, _install_intro_content())
        if updated:
            sections_updated.append("install_intro")
        why_key = _marker_key(markers.get("why_omg", "")) or "why-omg"
        content, updated = _upsert_section(content, why_key, _why_omg_content())
        if updated:
            sections_updated.append("why_omg")
        readme.write_text(content, encoding="utf-8")

    changelog = root / "CHANGELOG.md"
    if changelog.exists():
        content = changelog.read_text(encoding="utf-8")
        cl_key = _marker_key(markers.get("changelog_current", "")) or f"changelog-v{CANONICAL_VERSION}"
        content, updated = _upsert_section(
            content, cl_key, _compile_release_text(CANONICAL_VERSION),
            insert_after="# Changelog",
        )
        if updated:
            sections_updated.append("changelog_current")
        changelog.write_text(content, encoding="utf-8")

    fast_path_marker = markers.get("install_fast_path", "")
    fp_key = _marker_key(fast_path_marker) or "install-fast-path"
    install_surfaces = [
        s for s in surfaces
        if s.get("marker") == fast_path_marker
        and s["category"] == "docs"
        and "docs/install/" in s.get("path", "")
    ]
    for surface in install_surfaces:
        guide_path = root / surface["path"]
        if guide_path.exists():
            content = guide_path.read_text(encoding="utf-8")
            content, updated = _upsert_section(content, fp_key, _install_fast_path_content())
            if updated:
                sections_updated.append(f"install_fast_path:{surface['id']}")
            guide_path.write_text(content, encoding="utf-8")

    proof_doc = root / "docs" / "proof.md"
    if proof_doc.exists():
        content = proof_doc.read_text(encoding="utf-8")
        pq_key = _marker_key(markers.get("proof_quickstart", "")) or "proof-quickstart"
        content, updated = _upsert_section(content, pq_key, _proof_quickstart_content())
        if updated:
            sections_updated.append("proof_quickstart")
        proof_doc.write_text(content, encoding="utf-8")

    qr_path = root / "QUICK-REFERENCE.md"
    if qr_path.exists():
        content = qr_path.read_text(encoding="utf-8")
        qr_key = _marker_key(markers.get("quick_reference_hosts", "")) or "quick-reference-hosts"
        content, updated = _upsert_section(content, qr_key, _quick_reference_hosts_content())
        if updated:
            sections_updated.append("quick_reference_hosts")
        qr_path.write_text(content, encoding="utf-8")

    vi_path = root / "INSTALL-VERIFICATION-INDEX.md"
    if vi_path.exists():
        content = vi_path.read_text(encoding="utf-8")
        vi_key = _marker_key(markers.get("verification_index_targets", "")) or "verification-index-targets"
        content, updated = _upsert_section(content, vi_key, _verification_index_targets_content())
        if updated:
            sections_updated.append("verification_index_targets")
        vi_path.write_text(content, encoding="utf-8")

    cmd_surface_path = root / "docs" / "command-surface.md"
    cmd_surface_path.parent.mkdir(parents=True, exist_ok=True)
    _write_command_surface_doc(cmd_surface_path, root)
    artifacts.append(str(cmd_surface_path.relative_to(root)))

    return {"status": "ok", "artifacts": artifacts, "sections_updated": sections_updated}


def _build_manifest(surfaces: list[dict[str, Any]], timestamp: str) -> dict[str, Any]:
    return {
        "generated_by": "omg release compile-surfaces",
        "version": CANONICAL_VERSION,
        "generated_at": timestamp,
        "surfaces": surfaces,
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _ = path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )


def _compile_release_text(version: str) -> str:
    return (
        f"### Governed Release Surface (v{version})\n"
        "\n"
        "- Canonical release surface compilation\n"
        "- Dual-channel artifact output (public + enterprise)\n"
        "- Idempotent generated-section markers in docs"
    )


def _release_notes_content() -> str:
    canonical = _compile_release_text(CANONICAL_VERSION)
    return (
        f"# OMG v{CANONICAL_VERSION} Release Notes\n"
        "\n"
        f"{canonical}\n"
        "\n"
        "## Artifacts\n"
        "\n"
        "- `dist/public/release-surface.json`\n"
        "- `dist/enterprise/release-surface.json`\n"
        "- `docs/command-surface.md`\n"
    )


def _release_body_content() -> str:
    canonical = _compile_release_text(CANONICAL_VERSION)
    return (
        f"# OMG v{CANONICAL_VERSION}\n"
        "\n"
        f"{canonical}\n"
        "\n"
        "See [CHANGELOG.md](../../CHANGELOG.md) for full history.\n"
    )


def _tag_body_content() -> str:
    canonical = _compile_release_text(CANONICAL_VERSION)
    return (
        f"OMG v{CANONICAL_VERSION}\n"
        "\n"
        f"{canonical}\n"
    )


def _marker_key(marker: str) -> str:
    m = re.match(r"<!--\s*OMG:GENERATED:(.+?)\s*-->", marker)
    return m.group(1) if m else ""


def _upsert_section(
    content: str,
    key: str,
    section_body: str,
    *,
    insert_after: str | None = None,
) -> tuple[str, bool]:
    open_tag = f"<!-- OMG:GENERATED:{key} -->"
    close_tag = f"<!-- /OMG:GENERATED:{key} -->"
    block = f"{open_tag}\n{section_body}\n{close_tag}"

    pattern = re.compile(
        re.escape(open_tag) + r".*?" + re.escape(close_tag), re.DOTALL,
    )

    if pattern.search(content):
        content = pattern.sub(block, content)
        return content, True

    if insert_after is not None:
        idx = content.find(insert_after)
        if idx >= 0:
            line_end = content.find("\n", idx)
            if line_end < 0:
                line_end = len(content)
            content = content[: line_end + 1] + "\n" + block + "\n" + content[line_end + 1 :]
            return content, True

    content = content.rstrip("\n") + "\n\n" + block + "\n"
    return content, True


def _quickstart_content() -> str:
    return (
        "Install OMG, check your environment, preview, then apply:\n"
        "\n"
        "```bash\n"
        "npm install -g @trac3er/oh-my-god\n"
        "omg env doctor\n"
        "omg install --plan\n"
        "omg install --apply\n"
        "```\n"
        "\n"
        "For project-local usage without a global install:\n"
        "`npm install @trac3er/oh-my-god` and then `npm exec omg -- <args>`.\n"
        "\n"
        "Then start working:\n"
        "\n"
        "```bash\n"
        "omg ship\n"
        "omg proof open --html\n"
        "omg blocked --last\n"
        "```\n"
        "\n"
        "> Compatibility: `/OMG:crazy <goal>` is still accepted as an alias."
    )


def _install_fast_path_content() -> str:
    return (
        "## Fast Path\n"
        "\n"
        "> **Prerequisite**: Node >=18\n"
        "\n"
        "```bash\n"
        "npm install -g @trac3er/oh-my-god  # put omg on PATH\n"
        "omg env doctor                     # check environment\n"
        "omg install --plan                 # preview changes\n"
        "omg install --apply                # apply configuration\n"
        "```\n"
        "\n"
        "For project-local usage: `npm install @trac3er/oh-my-god`.\n"
        "Then run commands through `npm exec omg -- <args>`.\n"
        "\n"
        "`npm install` performs dependency resolution and bin linking.\n"
        "The `postinstall` hook runs `--plan` only (no mutations).\n"
        "Mutation requires explicit `omg install --apply`."
    )


def _proof_content() -> str:
    return (
        "## Verification\n"
        "\n"
        "```bash\n"
        "omg proof open --html\n"
        "omg blocked --last\n"
        "omg explain run <id>\n"
        "omg budget simulate --enforce\n"
        "```\n"
        "\n"
        "Machine-generated evidence artifacts: `.omg/evidence/`"
    )


def _install_intro_content() -> str:
    return (
        "## Quickstart\n"
        "\n"
        "```bash\n"
        "npm install -g @trac3er/oh-my-god\n"
        "omg env doctor              # check your environment\n"
        "omg install --plan          # preview what OMG will configure\n"
        "omg install --apply         # apply configuration\n"
        "omg ship                    # start working\n"
        "```\n"
        "\n"
        "`npm install @trac3er/oh-my-god` handles dependency resolution and bin linking only.\n"
        "The `postinstall` hook runs `omg install --plan` (preview, no mutations).\n"
        "To apply changes, run `omg install --apply` explicitly.\n"
        "\n"
        "For global installation: `npm install -g @trac3er/oh-my-god` to get `omg` on PATH.\n"
        "For local without global: `npm install @trac3er/oh-my-god`, then `npm exec omg -- <args>`.\n"
        "\n"
        "On non-Claude hosts, verify native MCP registration:\n"
        "\n"
        "- `codex mcp list`\n"
        "- `gemini mcp list`\n"
        "- `kimi mcp list`"
    )


def _why_omg_content() -> str:
    return (
        "## Why OMG\n"
        "\n"
        "- Multi-host support: Claude Code, Codex, Gemini CLI, and Kimi CLI are canonical behavior-parity hosts; OpenCode is compatibility-only.\n"
        "- Compiled planning: advanced planning is compiled into the `plan-council` bundle for deterministic execution.\n"
        "- Native adoption: setup detects OMC, OMX, and Superpowers-style environments without exposing copycat public migration commands.\n"
        "- Proof-first delivery: verification, provider coverage, HUD artifacts, and transcripts are published instead of implied.\n"
        "\n"
        "> Compatibility: `/OMG:setup`, `/OMG:crazy`, `/OMG:browser` etc. remain as Claude Code slash-command aliases."
    )


def _proof_quickstart_content() -> str:
    return (
        "## Getting Started with Proof\n"
        "\n"
        "```bash\n"
        "omg proof open --html       # open latest evidence pack as narrated proof\n"
        "omg blocked --last          # inspect last governance block explanation\n"
        "omg explain run <id>        # explain a specific run\n"
        "omg budget simulate --enforce\n"
        "```\n"
        "\n"
        "Machine-generated evidence artifacts: `.omg/evidence/`"
    )


def _quick_reference_hosts_content() -> str:
    return (
        "### Canonical Hosts\n"
        "\n"
        "| Host | Config File |\n"
        "| :--- | :--- |\n"
        "| claude | `.mcp.json` |\n"
        "| codex | `~/.codex/config.toml` |\n"
        "| gemini | `~/.gemini/settings.json` |\n"
        "| kimi | `~/.kimi/mcp.json` |\n"
        "\n"
        "### Compatibility Hosts\n"
        "\n"
        "| Host | Config File |\n"
        "| :--- | :--- |\n"
        "| opencode | `~/.config/opencode/opencode.json` |"
    )


def _verification_index_targets_content() -> str:
    return (
        "## Installation Targets & Methods\n"
        "\n"
        "### Canonical Targets\n"
        "1. **Claude** — Config: `.mcp.json`\n"
        "2. **Codex** — Config: `~/.codex/config.toml`\n"
        "3. **Gemini** — Config: `~/.gemini/settings.json`\n"
        "4. **Kimi** — Config: `~/.kimi/mcp.json`\n"
        "\n"
        "### Compatibility Targets\n"
        "5. **OpenCode** — Config: `~/.config/opencode/opencode.json`"
    )


def _command_surface_snippet(root: Path) -> str:
    promoted = get_promoted_public_commands()
    if not promoted:
        return "No commands available."
    return "\n".join(f"- `{cmd}`" for cmd in promoted)


def _extract_commands(root: Path) -> list[tuple[str, str]]:
    omg_py = root / "scripts" / "omg.py"
    if not omg_py.exists():
        return []

    try:
        tree = ast.parse(omg_py.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    build_fn: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_parser":
            build_fn = node
            break

    search_root: ast.AST = build_fn if build_fn is not None else tree
    main_var = _find_main_subparser_var(search_root)

    commands: list[tuple[str, str]] = []
    seen: set[str] = set()
    for node in ast.walk(search_root):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_parser"):
            continue
        if main_var is not None:
            if not (isinstance(func.value, ast.Name) and func.value.id == main_var):
                continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        name = str(node.args[0].value)
        if name in seen:
            continue
        seen.add(name)

        help_text = ""
        for kw in node.keywords:
            if kw.arg == "help" and isinstance(kw.value, ast.Constant):
                help_text = str(kw.value.value)
        commands.append((name, help_text))

    return commands


def _find_main_subparser_var(root: ast.AST) -> str | None:
    for node in ast.walk(root):
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        val = node.value
        if not isinstance(val, ast.Call):
            continue
        func = val.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_subparsers"):
            continue
        for kw in val.keywords:
            if (
                kw.arg == "dest"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "command"
            ):
                return node.targets[0].id
    return None


def _write_command_surface_doc(path: Path, root: Path) -> None:
    commands = _extract_commands(root)
    lines = [
        "<!-- GENERATED: DO NOT EDIT MANUALLY -->",
        f"# OMG Command Surface",
        "",
        f"Generated for OMG v{CANONICAL_VERSION}.",
        "",
    ]
    if commands:
        lines.append("## Commands")
        lines.append("")
        lines.append("| Command | Description |")
        lines.append("| :--- | :--- |")
        for name, help_text in commands:
            lines.append(f"| `omg {name}` | {help_text or chr(8212)} |")

    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _extract_marker_content(content: str, key: str) -> str | None:
    open_tag = f"<!-- OMG:GENERATED:{key} -->"
    close_tag = f"<!-- /OMG:GENERATED:{key} -->"
    pattern = re.compile(
        re.escape(open_tag) + r"\n(.*?)\n" + re.escape(close_tag), re.DOTALL,
    )
    m = pattern.search(content)
    return m.group(1) if m else None


def _check_marker_drift(
    root: Path,
    rel_path: str,
    marker: str,
    expected_body: str,
    surface_name: str,
    drift: list[dict[str, str]],
) -> None:
    path = root / rel_path
    if not path.exists():
        return
    key = _marker_key(marker)
    if not key:
        return
    actual = _extract_marker_content(path.read_text(encoding="utf-8"), key)
    if actual is None:
        drift.append({"surface": surface_name, "path": rel_path, "reason": "marker block not found"})
    elif actual != expected_body:
        drift.append({"surface": surface_name, "path": rel_path, "reason": "content drift in generated block"})


def _check_artifact_drift(
    root: Path,
    rel_path: str,
    expected_content: str,
    surface_name: str,
    drift: list[dict[str, str]],
) -> None:
    path = root / rel_path
    if not path.exists():
        drift.append({"surface": surface_name, "path": rel_path, "reason": "artifact file missing"})
        return
    if path.read_text(encoding="utf-8") != expected_content:
        drift.append({"surface": surface_name, "path": rel_path, "reason": "artifact content drift"})


def _check_release_surfaces(root: Path) -> dict[str, Any]:
    markers = get_generated_section_markers()
    drift: list[dict[str, str]] = []

    canonical = _compile_release_text(CANONICAL_VERSION)

    _check_marker_drift(
        root, "CHANGELOG.md",
        markers.get("changelog_current", ""),
        canonical, "changelog_current", drift,
    )
    _check_marker_drift(
        root, "README.md",
        markers.get("readme_quickstart", ""),
        _quickstart_content(), "readme_quickstart", drift,
    )
    _check_marker_drift(
        root, "README.md",
        markers.get("readme_command_surface", ""),
        _command_surface_snippet(root), "readme_command_surface", drift,
    )
    _check_marker_drift(
        root, "README.md",
        markers.get("proof_generated_section", ""),
        _proof_content(), "proof_generated_section", drift,
    )
    _check_marker_drift(
        root, "README.md",
        markers.get("install_intro", ""),
        _install_intro_content(), "install_intro", drift,
    )
    _check_marker_drift(
        root, "README.md",
        markers.get("why_omg", ""),
        _why_omg_content(), "why_omg", drift,
    )
    _check_marker_drift(
        root, "docs/proof.md",
        markers.get("proof_quickstart", ""),
        _proof_quickstart_content(), "proof_quickstart", drift,
    )
    _check_marker_drift(
        root, "QUICK-REFERENCE.md",
        markers.get("quick_reference_hosts", ""),
        _quick_reference_hosts_content(), "quick_reference_hosts", drift,
    )
    _check_marker_drift(
        root, "INSTALL-VERIFICATION-INDEX.md",
        markers.get("verification_index_targets", ""),
        _verification_index_targets_content(), "verification_index_targets", drift,
    )

    _check_artifact_drift(
        root, f"artifacts/release/release-notes-v{CANONICAL_VERSION}.md",
        _release_notes_content(), "release_notes", drift,
    )
    _check_artifact_drift(
        root, f"artifacts/release/release-body-v{CANONICAL_VERSION}.md",
        _release_body_content(), "github_release_body", drift,
    )
    _check_artifact_drift(
        root, f"artifacts/release/tag-body-v{CANONICAL_VERSION}.md",
        _tag_body_content(), "tag_body", drift,
    )

    return {"status": "ok" if not drift else "drift", "drift": drift}
