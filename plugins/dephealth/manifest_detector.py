"""Package manifest detector — scans project directories for dependency manifests.

Supports: package.json, requirements.txt, Cargo.toml, go.mod, Gemfile, pyproject.toml.
Returns a unified DependencyList with all discovered packages.

stdlib only — no external dependencies.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ManifestFile:
    """Represents a discovered manifest file."""

    path: str
    format: str


@dataclass
class Package:
    """Represents a single dependency package."""

    name: str
    version: str
    dev: bool
    source_manifest: str


@dataclass
class DependencyList:
    """Unified result of manifest detection."""

    manifests: list[ManifestFile] = field(default_factory=list)
    packages: list[Package] = field(default_factory=list)


# ─── Known manifest filenames ────────────────────────────────────────────────

_MANIFEST_FILES: list[tuple[str, str]] = [
    ("package.json", "package.json"),
    ("requirements.txt", "requirements.txt"),
    ("Cargo.toml", "Cargo.toml"),
    ("go.mod", "go.mod"),
    ("Gemfile", "Gemfile"),
    ("pyproject.toml", "pyproject.toml"),
]


# ─── Parsers ─────────────────────────────────────────────────────────────────


def _parse_package_json(file_path: str) -> list[Package]:
    """Parse package.json for dependencies and devDependencies."""
    packages: list[Package] = []
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return packages

    deps = data.get("dependencies", {})
    if isinstance(deps, dict):
        for name, version in deps.items():
            packages.append(Package(
                name=name,
                version=str(version),
                dev=False,
                source_manifest=file_path,
            ))

    dev_deps = data.get("devDependencies", {})
    if isinstance(dev_deps, dict):
        for name, version in dev_deps.items():
            packages.append(Package(
                name=name,
                version=str(version),
                dev=True,
                source_manifest=file_path,
            ))

    return packages


def _parse_requirements_txt(file_path: str) -> list[Package]:
    """Parse requirements.txt (name==version, name>=version, or bare name)."""
    packages: list[Package] = []
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
    except OSError:
        return packages

    # Matches: name==version, name>=version, name<=version, name~=version, name!=version
    req_re = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9._-]*)\s*(?:[><=!~]+\s*(.+))?$")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = req_re.match(line)
        if m:
            name = m.group(1)
            version = m.group(2) or ""
            packages.append(Package(
                name=name,
                version=version.strip(),
                dev=False,
                source_manifest=file_path,
            ))

    return packages


def _parse_cargo_toml(file_path: str) -> list[Package]:
    """Parse Cargo.toml [dependencies] and [dev-dependencies] via regex."""
    packages: list[Package] = []
    try:
        with open(file_path, "r") as f:
            content = f.read()
    except OSError:
        return packages

    # Split into sections by [header]
    section_re = re.compile(r"^\[([^\]]+)\]\s*$", re.MULTILINE)
    sections: dict[str, str] = {}
    positions = [(m.group(1).strip(), m.end()) for m in section_re.finditer(content)]

    for i, (name, start) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(content)
        # Adjust end to be the start of the next section header line
        if i + 1 < len(positions):
            # Find the start of the next header line
            next_header_start = content.rfind("[", start, end)
            if next_header_start >= 0:
                end = next_header_start
        sections[name] = content[start:end]

    # Parse dependency lines: name = "version" or name = { version = "ver", ... }
    dep_line_re = re.compile(
        r'^([A-Za-z0-9_][A-Za-z0-9_-]*)\s*=\s*(?:"([^"]+)"|'
        r'\{[^}]*version\s*=\s*"([^"]+)"[^}]*\})',
        re.MULTILINE,
    )

    for section_name, section_body in sections.items():
        is_dev = "dev-dependencies" in section_name.lower()
        is_dep = "dependencies" in section_name.lower()
        if not is_dep:
            continue

        for m in dep_line_re.finditer(section_body):
            name = m.group(1)
            version = m.group(2) or m.group(3) or ""
            packages.append(Package(
                name=name,
                version=version,
                dev=is_dev,
                source_manifest=file_path,
            ))

    return packages


def _parse_go_mod(file_path: str) -> list[Package]:
    """Parse go.mod require block."""
    packages: list[Package] = []
    try:
        with open(file_path, "r") as f:
            content = f.read()
    except OSError:
        return packages

    # Match require ( ... ) block
    require_block_re = re.compile(r"require\s*\(\s*(.*?)\s*\)", re.DOTALL)
    for block_m in require_block_re.finditer(content):
        block = block_m.group(1)
        for line in block.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                packages.append(Package(
                    name=parts[0],
                    version=parts[1],
                    dev=False,
                    source_manifest=file_path,
                ))

    # Also match single-line require: require github.com/foo/bar v1.0.0
    single_re = re.compile(r"^require\s+(\S+)\s+(\S+)", re.MULTILINE)
    for m in single_re.finditer(content):
        packages.append(Package(
            name=m.group(1),
            version=m.group(2),
            dev=False,
            source_manifest=file_path,
        ))

    return packages


def _parse_gemfile(file_path: str) -> list[Package]:
    """Parse Gemfile gem declarations."""
    packages: list[Package] = []
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
    except OSError:
        return packages

    # gem "name", "version" or gem 'name', 'version' or gem "name"
    gem_re = re.compile(
        r"""gem\s+['"]([^'"]+)['"]\s*(?:,\s*['"]([^'"]+)['"])?"""
    )

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = gem_re.search(line)
        if m:
            name = m.group(1)
            version = m.group(2) or ""
            packages.append(Package(
                name=name,
                version=version,
                dev=False,
                source_manifest=file_path,
            ))

    return packages


def _parse_pyproject_toml(file_path: str) -> list[Package]:
    """Parse pyproject.toml for [project.dependencies] and optional-dependencies."""
    packages: list[Package] = []
    try:
        with open(file_path, "r") as f:
            content = f.read()
    except OSError:
        return packages

    # Extract PEP 508 name and version from dependency string like "fastapi>=0.100.0"
    pep508_re = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9._-]*)\s*(.*)$")

    def _extract_deps_from_array(text: str, is_dev: bool) -> list[Package]:
        """Extract packages from a TOML array literal."""
        result: list[Package] = []
        # Match quoted strings inside brackets
        str_re = re.compile(r'["\']([^"\']+)["\']')
        for m in str_re.finditer(text):
            dep_str = m.group(1).strip()
            pm = pep508_re.match(dep_str)
            if pm:
                name = pm.group(1)
                version = pm.group(2).strip()
                result.append(Package(
                    name=name,
                    version=version,
                    dev=is_dev,
                    source_manifest=file_path,
                ))
        return result

    # Find dependencies = [...] under [project]
    # Simple approach: find "dependencies = [" after [project] section
    project_deps_re = re.compile(
        r"\[project\].*?^dependencies\s*=\s*\[(.*?)\]",
        re.MULTILINE | re.DOTALL,
    )
    pm = project_deps_re.search(content)
    if pm:
        packages.extend(_extract_deps_from_array(pm.group(1), is_dev=False))

    # Find [project.optional-dependencies] sections
    opt_deps_re = re.compile(
        r"\[project\.optional-dependencies\].*?$",
        re.MULTILINE,
    )
    om = opt_deps_re.search(content)
    if om:
        # Extract the section body until next [section] or end of file
        start = om.end()
        next_section = re.search(r"^\[", content[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(content)
        section_body = content[start:end]

        # Find key = [...] arrays (e.g., dev = ["pytest>=7.4.0"])
        array_re = re.compile(r"^\w+\s*=\s*\[(.*?)\]", re.MULTILINE | re.DOTALL)
        for am in array_re.finditer(section_body):
            packages.extend(_extract_deps_from_array(am.group(1), is_dev=True))

    # Also support [tool.poetry.dependencies] pattern
    poetry_deps_re = re.compile(
        r"\[tool\.poetry\.dependencies\](.*?)(?=\[|$)",
        re.DOTALL,
    )
    pm = poetry_deps_re.search(content)
    if pm:
        section_body = pm.group(1)
        # Poetry deps: name = "version" or name = {version = "ver"}
        dep_line_re = re.compile(
            r'^([A-Za-z0-9_][A-Za-z0-9._-]*)\s*=\s*(?:"([^"]+)"|'
            r"\{[^}]*version\s*=\s*\"([^\"]+)\"[^}]*\})",
            re.MULTILINE,
        )
        for dm in dep_line_re.finditer(section_body):
            name = dm.group(1)
            if name.lower() == "python":
                continue  # Skip python version constraint
            version = dm.group(2) or dm.group(3) or ""
            packages.append(Package(
                name=name,
                version=version,
                dev=False,
                source_manifest=file_path,
            ))

    # [tool.poetry.dev-dependencies]
    poetry_dev_re = re.compile(
        r"\[tool\.poetry\.dev-dependencies\](.*?)(?=\[|$)",
        re.DOTALL,
    )
    pm = poetry_dev_re.search(content)
    if pm:
        section_body = pm.group(1)
        dep_line_re = re.compile(
            r'^([A-Za-z0-9_][A-Za-z0-9._-]*)\s*=\s*(?:"([^"]+)"|'
            r"\{[^}]*version\s*=\s*\"([^\"]+)\"[^}]*\})",
            re.MULTILINE,
        )
        for dm in dep_line_re.finditer(section_body):
            name = dm.group(1)
            version = dm.group(2) or dm.group(3) or ""
            packages.append(Package(
                name=name,
                version=version,
                dev=True,
                source_manifest=file_path,
            ))

    return packages


# ─── Parser dispatch ─────────────────────────────────────────────────────────

_PARSERS: dict[str, Any] = {
    "package.json": _parse_package_json,
    "requirements.txt": _parse_requirements_txt,
    "Cargo.toml": _parse_cargo_toml,
    "go.mod": _parse_go_mod,
    "Gemfile": _parse_gemfile,
    "pyproject.toml": _parse_pyproject_toml,
}


# ─── Public API ──────────────────────────────────────────────────────────────


def _dep_health_enabled() -> bool:
    env_val = os.environ.get("OMG_DEP_HEALTH_ENABLED", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from hooks._common import get_feature_flag
        return get_feature_flag("DEP_HEALTH", default=False)
    except Exception:
        return False


def detect_manifests(project_dir: str) -> DependencyList:
    """Scan project_dir for manifest files and return a unified DependencyList.

    Supports: package.json, requirements.txt, Cargo.toml, go.mod, Gemfile, pyproject.toml.
    Gracefully handles missing/malformed files (skips, no crash).
    """
    if not _dep_health_enabled():
        return DependencyList()
    
    result = DependencyList()
    project_path = Path(project_dir)

    if not project_path.is_dir():
        return result

    for filename, fmt in _MANIFEST_FILES:
        file_path = project_path / filename
        if not file_path.is_file():
            continue

        parser = _PARSERS.get(fmt)
        if not parser:
            continue

        try:
            packages = parser(str(file_path))
            if packages:
                result.manifests.append(ManifestFile(
                    path=str(file_path),
                    format=fmt,
                ))
                result.packages.extend(packages)
        except Exception:
            # Graceful degradation: skip malformed files
            continue

    return result
