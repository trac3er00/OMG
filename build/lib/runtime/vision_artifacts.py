"""Artifact writers for vision runtime jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_vision_artifacts(
    project_dir: str,
    job: dict[str, Any],
    deterministic_results: list[dict[str, Any]],
) -> dict[str, Any]:
    artifacts_dir = Path(project_dir) / ".omg" / "vision"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifacts_dir / f"{job['job_id']}.json"
    payload = {
        "schema": "VisionJobArtifact",
        "job": job,
        "results": deterministic_results,
    }
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "artifact_path": str(artifact_path.relative_to(project_dir)),
        "compare_count": sum(1 for item in deterministic_results if item.get("operation") == "compare"),
        "ocr_count": sum(1 for item in deterministic_results if item.get("operation") == "ocr"),
        "result_count": len(deterministic_results),
    }
