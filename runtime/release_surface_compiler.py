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
)


def compile_release_surfaces(root: Path) -> dict[str, Any]:
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

    notes_path = root / "artifacts" / "release" / f"release-notes-v{CANONICAL_VERSION}.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    _write_release_notes(notes_path)
    artifacts.append(str(notes_path.relative_to(root)))

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
        readme.write_text(content, encoding="utf-8")

    changelog = root / "CHANGELOG.md"
    if changelog.exists():
        content = changelog.read_text(encoding="utf-8")
        cl_key = _marker_key(markers.get("changelog_current", "")) or f"changelog-v{CANONICAL_VERSION}"
        content, updated = _upsert_section(
            content, cl_key, _changelog_content(), insert_after="# Changelog",
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


def _write_release_notes(path: Path) -> None:
    _ = path.write_text(
        f"# OMG v{CANONICAL_VERSION} Release Notes\n"
        "\n"
        "## Highlights\n"
        "\n"
        "- Governed release surface compilation\n"
        "- Dual-channel artifact output (public + enterprise)\n"
        "\n"
        "## Changes\n"
        "\n"
        "See [CHANGELOG.md](../../CHANGELOG.md) for full details.\n"
        "\n"
        "## Artifacts\n"
        "\n"
        "- `dist/public/release-surface.json`\n"
        "- `dist/enterprise/release-surface.json`\n"
        "- `docs/command-surface.md`\n",
        encoding="utf-8",
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
        "Install with npm or bunx:\n"
        "\n"
        "```bash\n"
        "npm install @trac3er/oh-my-god\n"
        "# or\n"
        "bunx @trac3er/oh-my-god\n"
        "```\n"
        "\n"
        "Then run:\n"
        "\n"
        "```text\n"
        "/OMG:setup\n"
        "/OMG:browser <goal>\n"
        "/OMG:crazy <goal>\n"
        "```"
    )


def _changelog_content() -> str:
    return (
        f"### Governed Release Surface (v{CANONICAL_VERSION})\n"
        "\n"
        "- Canonical release surface compilation\n"
        "- Dual-channel manifests (public + enterprise)\n"
        "- Idempotent generated-section markers in docs"
    )


def _install_fast_path_content() -> str:
    return (
        "## Fast Path\n"
        "\n"
        "```bash\n"
        "npm install @trac3er/oh-my-god\n"
        "# or\n"
        "bunx @trac3er/oh-my-god\n"
        "```\n"
        "\n"
        "This registers the OMG control plane for your host automatically."
    )


def _command_surface_snippet(root: Path) -> str:
    commands = _extract_commands(root)
    if not commands:
        return "No commands extracted."
    return "\n".join(f"- `omg {name}`" for name, _ in commands[:15])


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
