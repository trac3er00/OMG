#!/usr/bin/env python3
"""Check that the repo is safe and polished enough for a public launch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

# Add root to sys.path to import runtime.adoption
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.adoption import CANONICAL_VERSION

REQUIRED_PUBLIC_DOCS = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
]

REQUIRED_COMMUNITY_TEMPLATES = [
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/pull_request_template.md",
]

PUBLIC_DOC_GLOBS = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "docs/**/*.md",
    "plugins/README.md",
    ".github/**/*.md",
]

TEXT_GLOBS = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "docs/**/*.md",
    "commands/**/*.md",
    "plugins/**/*.md",
    "agents/**/*.md",
    "rules/**/*.md",
    "runtime/**/*.py",
    "hooks/**/*.py",
    "scripts/**/*.py",
    ".github/workflows/**/*.yml",
    ".github/workflows/**/*.yaml",
    "OMG-setup.sh",
    "install.sh",
    "package.json",
    "settings.json",
    ".claude-plugin/**/*.json",
    "plugins/**/*.json",
]

MARKDOWN_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|\[[^\]]+\]\(([^)]+)\)")
HTTP_URL_RE = re.compile(r"https?://[^\s)\]>'\"]+")
ALLOW_PATTERN_REFERENCES = {
    ROOT / "scripts" / "check-omg-public-ready.py",
    ROOT / "scripts" / "check-omg-standalone-clean.py",
    ROOT / "scripts" / "omg.py",
}
ALLOW_DEPRECATED_MARKETPLACE = {
    ROOT / "OMG-setup.sh",
    ROOT / "scripts" / "check-omg-public-ready.py",
}


def _iter_files(root: Path, globs: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in globs:
        files.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(files))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_text_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in _iter_files(root, TEXT_GLOBS):
        rel = path.relative_to(root)
        content = _read(path)
        if "/Users/" in content:
            if path not in ALLOW_PATTERN_REFERENCES:
                violations.append(f"{rel}: absolute local path found in public repo content")
        if ".sisyphus/" in content:
            if path not in ALLOW_PATTERN_REFERENCES:
                violations.append(f"{rel}: stale internal path reference found (.sisyphus/)")
        if "trac3r00/OAL" in content:
            if path not in ALLOW_PATTERN_REFERENCES:
                violations.append(f"{rel}: old repo identifier found (trac3r00/OAL)")
        if "oh-advanced-layer" in content:
            if path not in ALLOW_DEPRECATED_MARKETPLACE:
                violations.append(f"{rel}: deprecated marketplace identifier found (oh-advanced-layer)")
    return violations


def _find_missing_docs(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in REQUIRED_PUBLIC_DOCS:
        if not (root / rel).exists():
            violations.append(f"{rel}: missing required public doc")
    return violations


def _find_missing_templates(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in REQUIRED_COMMUNITY_TEMPLATES:
        if not (root / rel).exists():
            violations.append(f"{rel}: missing required community template")
    return violations


def _find_internal_docs(root: Path) -> list[str]:
    violations: list[str] = []
    plans_dir = root / "docs" / "plans"
    if plans_dir.exists() and any(path.is_file() for path in plans_dir.rglob("*")):
        violations.append("docs/plans/: internal planning docs must not ship in public branch")
    return violations


def _normalize_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return target


def _is_relative_markdown_link(target: str) -> bool:
    if not target:
        return False
    if target.startswith("#"):
        return False
    lowered = target.lower()
    return not (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("data:")
        or lowered.startswith("file:")
        or target.startswith("/")
    )


def _link_target_exists(doc_path: Path, target: str) -> bool:
    file_part = target.split("#", 1)[0].split("?", 1)[0]
    if not file_part:
        return True
    resolved = (doc_path.parent / file_part).resolve()
    return resolved.exists()


def _find_broken_markdown_links(root: Path) -> list[str]:
    violations: list[str] = []
    for path in _iter_files(root, PUBLIC_DOC_GLOBS):
        rel = path.relative_to(root)
        content = _read(path)
        for match in MARKDOWN_LINK_RE.finditer(content):
            target = _normalize_link_target(match.group(1) or match.group(2) or "")
            if not _is_relative_markdown_link(target):
                continue
            if not _link_target_exists(path, target):
                violations.append(f"{rel}: broken markdown link -> {target}")
    return violations


def _is_loopback_host(hostname: str) -> bool:
    lowered = hostname.strip().lower()
    return lowered in {"localhost", "127.0.0.1", "::1"}


def _find_proof_surface_violations(root: Path) -> list[str]:
    violations: list[str] = []
    proof_path = root / "docs" / "proof.md"
    if not proof_path.exists():
        violations.append("docs/proof.md: missing proof surface document")
        return violations

    content = _read(proof_path)
    lowered = content.lower()
    hardcoded_counts = bool(
        re.search(r"\b\d+\s*/\s*\d+\b", lowered)
        or re.search(r"\b\d+\s+(tests?|checks?|providers?)\s+(passed|pass|green|successful)\b", lowered)
        or re.search(r"\ball\s+tests?\s+passed\b", lowered)
    )
    has_artifact_refs = any(
        token in content
        for token in (
            ".omg/evidence/",
            ".omg/evals/",
            ".omg/tracebank/",
            ".omg/lineage/",
        )
    )
    if hardcoded_counts and not has_artifact_refs:
        violations.append("docs/proof.md: prose-only proof counts found without machine artifact references")

    if ".omg/evidence/doctor.json" not in content:
        violations.append("docs/proof.md: missing doctor output artifact reference (.omg/evidence/doctor.json)")

    for path in _iter_files(root, PUBLIC_DOC_GLOBS):
        rel = path.relative_to(root)
        for line in _read(path).splitlines():
            if "production" not in line.lower():
                continue
            for url in HTTP_URL_RE.findall(line):
                parsed = urlparse(url)
                if parsed.scheme != "http":
                    continue
                host = parsed.hostname or ""
                if host and not _is_loopback_host(host):
                    violations.append(
                        f"{rel}: production claim uses non-loopback HTTP endpoint ({url})"
                    )
    return violations


def _find_doc_currency_violations(root: Path) -> list[str]:
    violations: list[str] = []
    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.exists():
        violations.append("CHANGELOG.md: missing changelog file")
        return violations

    content = _read(changelog_path)
    # Look for version in headers like ## [2.0.7] or ## 2.0.7
    version_pattern = re.compile(rf"##\s*\[?{re.escape(CANONICAL_VERSION)}\]?")
    if not version_pattern.search(content):
        violations.append(
            f"CHANGELOG.md: missing entry for current version {CANONICAL_VERSION}"
        )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OMG public-readiness hygiene")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()

    violations = []
    violations.extend(_find_missing_docs(root))
    violations.extend(_find_missing_templates(root))
    violations.extend(_find_internal_docs(root))
    violations.extend(_find_text_violations(root))
    violations.extend(_find_broken_markdown_links(root))
    violations.extend(_find_proof_surface_violations(root))
    violations.extend(_find_doc_currency_violations(root))
    violations = sorted(set(violations))

    if violations:
        print(json.dumps({"status": "error", "violations": violations}, indent=2))
        return 1

    print(json.dumps({"status": "ok", "message": "public readiness check passed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
