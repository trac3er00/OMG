"""Helpers for locating packaged OMG assets from source checkouts or installs."""
from __future__ import annotations

from importlib import metadata
from pathlib import Path


_DIST_NAMES = ("oh-my-god", "oh_my_god")


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_asset(rel_path: str | Path) -> Path:
    rel = Path(rel_path)
    candidate = project_root() / rel
    if candidate.exists():
        return candidate

    rel_posix = rel.as_posix()
    for dist_name in _DIST_NAMES:
        try:
            dist = metadata.distribution(dist_name)
        except metadata.PackageNotFoundError:
            continue
        for file in dist.files or []:
            if str(file).endswith(rel_posix):
                located = Path(dist.locate_file(file))
                if located.exists():
                    return located

    raise FileNotFoundError(f"Unable to resolve packaged OMG asset: {rel_posix}")


def resolve_assets(prefix: str | Path, suffix: str = "") -> list[Path]:
    prefix_path = Path(prefix)
    root_candidate = project_root() / prefix_path
    if root_candidate.exists():
        if root_candidate.is_dir():
            if suffix:
                return sorted(path for path in root_candidate.rglob("*") if path.is_file() and path.name.endswith(suffix))
            return sorted(path for path in root_candidate.rglob("*") if path.is_file())
        return [root_candidate]

    prefix_posix = prefix_path.as_posix().rstrip("/")
    matched: list[Path] = []
    for dist_name in _DIST_NAMES:
        try:
            dist = metadata.distribution(dist_name)
        except metadata.PackageNotFoundError:
            continue
        for file in dist.files or []:
            file_text = str(file)
            if not file_text.startswith(prefix_posix):
                continue
            if suffix and not file_text.endswith(suffix):
                continue
            located = Path(dist.locate_file(file))
            if located.exists() and located.is_file():
                matched.append(located)
    return sorted(matched)
