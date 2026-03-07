"""Lineage manifests for generated OMG artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_lineage_manifest(
    project_dir: str,
    *,
    artifact_type: str,
    sources: list[dict[str, Any]],
    privacy: str,
    license: str,
    derivation: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    lineage_id = f"lineage-{uuid4().hex}"
    payload = {
        "schema": "DataLineageManifest",
        "lineage_id": lineage_id,
        "generated_at": _now(),
        "artifact_type": artifact_type,
        "sources": sources,
        "privacy": privacy,
        "license": license,
        "derivation": derivation,
        "trace_id": trace_id or "",
    }
    validation = validate_lineage_manifest(payload)
    payload["status"] = validation["status"]
    payload["errors"] = validation["errors"]

    rel_path = Path(".omg") / "lineage" / f"{lineage_id}.json"
    path = Path(project_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["path"] = rel_path.as_posix()
    return payload


def validate_lineage_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not payload.get("artifact_type"):
        errors.append("artifact_type is required")
    if not payload.get("privacy"):
        errors.append("privacy is required")
    if not payload.get("license"):
        errors.append("license is required")
    sources = payload.get("sources", [])
    if not isinstance(sources, list) or not sources:
        errors.append("sources are required")
    else:
        for idx, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"source {idx} must be an object")
                continue
            if not source.get("license"):
                errors.append(f"source {idx} missing license")
            if not source.get("path"):
                errors.append(f"source {idx} missing path")
    return {
        "schema": "DataLineageValidationResult",
        "status": "ok" if not errors else "error",
        "errors": errors,
    }
