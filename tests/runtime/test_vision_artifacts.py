from __future__ import annotations

import json
from pathlib import Path

from runtime.vision_artifacts import write_vision_artifacts


def test_write_vision_artifacts_persists_json(tmp_path: Path) -> None:
    job = {
        "job_id": "vision-job-1",
        "mode": "compare",
        "inputs": [str(tmp_path / "a.png"), str(tmp_path / "b.png")],
    }
    deterministic_results = [
        {
            "status": "ok",
            "operation": "compare",
            "left_path": str(tmp_path / "a.png"),
            "right_path": str(tmp_path / "b.png"),
            "pixel_delta_ratio": 1.0,
        }
    ]

    artifact = write_vision_artifacts(str(tmp_path), job, deterministic_results)

    artifact_path = tmp_path / artifact["artifact_path"]
    assert artifact["compare_count"] == 1
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["job"]["job_id"] == "vision-job-1"
    assert payload["results"][0]["operation"] == "compare"
