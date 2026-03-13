"""Content-addressed cache helpers for vision jobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _cache_dir(project_dir: str) -> Path:
    path = Path(project_dir) / ".omg" / "cache" / "vision"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_cache_key(mode: str, inputs: list[str]) -> str:
    digest = hashlib.sha256()
    digest.update(mode.encode("utf-8"))
    for input_path in sorted(inputs):
        digest.update(input_path.encode("utf-8"))
        with open(input_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    return digest.hexdigest()


def load_cached_result(project_dir: str, cache_key: str) -> dict[str, Any] | None:
    cache_path = _cache_dir(project_dir) / f"{cache_key}.json"
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8"))


def store_cached_result(project_dir: str, cache_key: str, payload: dict[str, Any]) -> str:
    cache_path = _cache_dir(project_dir) / f"{cache_key}.json"
    cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(cache_path)
