"""Runtime orchestration for vision jobs."""

from __future__ import annotations

import hashlib
import itertools
from pathlib import Path
from typing import Any

from omg_natives.image import image

from runtime.vision_artifacts import write_vision_artifacts
from runtime.vision_cache import build_cache_key, load_cached_result, store_cached_result


VALID_VISION_MODES = frozenset({"ocr", "compare", "analyze", "batch", "eval"})


def _resolve_inputs(project_dir: str, inputs: list[str]) -> list[str]:
    return [str((Path(project_dir) / item).resolve()) for item in inputs]


def _job_id(mode: str, inputs: list[str]) -> str:
    digest = hashlib.sha256()
    digest.update(mode.encode("utf-8"))
    for item in inputs:
        digest.update(item.encode("utf-8"))
    return f"vision-{digest.hexdigest()[:12]}"


def normalize_vision_payload(project_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode", "")).strip()
    raw_inputs = payload.get("inputs")
    if mode not in VALID_VISION_MODES:
        raise ValueError(f"unsupported vision mode: {mode}")
    if not isinstance(raw_inputs, list) or not raw_inputs or not all(isinstance(item, str) and item.strip() for item in raw_inputs):
        raise ValueError("inputs must be a non-empty list of file paths")

    resolved_inputs = _resolve_inputs(project_dir, raw_inputs)
    for input_path in resolved_inputs:
        if not Path(input_path).exists():
            raise ValueError(f"missing vision input: {input_path}")

    return {
        "job_id": _job_id(mode, resolved_inputs),
        "mode": mode,
        "inputs": resolved_inputs,
    }


def expand_pairs(job: dict[str, Any]) -> list[tuple[str, str]]:
    if job["mode"] != "compare":
        return []
    return list(itertools.combinations(job["inputs"], 2))


def run_vision_job(project_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    job = normalize_vision_payload(project_dir, payload)
    cache_key = build_cache_key(job["mode"], job["inputs"])
    cached = load_cached_result(project_dir, cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    if job["mode"] == "compare":
        deterministic_results = [
            image(left_path, "compare", other_path=right_path)
            for left_path, right_path in expand_pairs(job)
        ]
    elif job["mode"] == "ocr":
        deterministic_results = [image(input_path, "ocr") for input_path in job["inputs"]]
    else:
        deterministic_results = []

    artifacts = write_vision_artifacts(project_dir, job, deterministic_results)
    result = {
        "status": "ok",
        "job": job,
        "results": deterministic_results,
        "artifacts": artifacts,
        "cached": False,
    }
    store_cached_result(project_dir, cache_key, result)
    return result
