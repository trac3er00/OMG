from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.forge_run_id import derive_run_seed
from runtime.repro_pack import build_repro_pack


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _evidence_pack_payload(*, include_determinism: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "EvidencePack",
        "schema_version": 2,
        "run_id": "run-1",
        "tests": [],
        "security_scans": [{"schema": "SecurityCheckResult", "path": ".omg/evidence/security-check.json"}],
        "diff_summary": {},
        "reproducibility": {},
        "unresolved_risks": ["risk:high:auth"],
        "trace_ids": ["trace-1", "trace-2"],
        "lineage": {"lineage_id": "lineage-1"},
        "executor": {},
        "environment": {},
        "artifacts": [
            {"kind": "browser_trace", "path": ".omg/evidence/browser-trace.zip", "trace_id": "trace-1"},
            {"kind": "incident_pack", "path": ".omg/incidents/incident-1.json", "trace_id": "trace-2"},
        ],
    }
    if include_determinism:
        payload.update(
            {
                "seed": derive_run_seed("run-1"),
                "temperature_lock": {
                    "critical_model_paths": 0.0,
                    "critical_tool_paths": 0.0,
                },
                "determinism_version": "forge-determinism-v1",
                "determinism_scope": "same-hardware",
            }
        )
    return payload


def _read_manifest(path: Path) -> dict[str, object]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _artifact_list(manifest: dict[str, object]) -> list[dict[str, object]]:
    artifacts = manifest.get("artifacts")
    assert isinstance(artifacts, list)
    artifacts_list = cast(list[object], artifacts)
    rows: list[dict[str, object]] = []
    for item in artifacts_list:
        if isinstance(item, dict):
            rows.append(cast(dict[str, object], item))
    return rows


def test_build_repro_pack_happy_path_assembles_manifest(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack_payload())
    _write_jsonl(
        tmp_path / ".omg" / "tracebank" / "events.jsonl",
        [
            {"trace_id": "trace-1", "status": "ok"},
            {"trace_id": "trace-2", "status": "ok"},
            {"trace_id": "trace-x", "status": "ignored"},
        ],
    )
    _write_json(tmp_path / ".omg" / "evals" / "latest.json", {"schema": "EvalGateResult", "trace_id": "trace-1"})
    _write_json(tmp_path / ".omg" / "lineage" / "lineage-1.json", {"lineage_id": "lineage-1", "schema": "LineageManifest"})
    _write_json(tmp_path / ".omg" / "evidence" / "security-check.json", {"schema": "SecurityCheckResult"})
    (tmp_path / ".omg" / "evidence" / "browser-trace.zip").parent.mkdir(parents=True, exist_ok=True)
    _ = (tmp_path / ".omg" / "evidence" / "browser-trace.zip").write_bytes(b"browser-proof")
    _write_json(tmp_path / ".omg" / "incidents" / "incident-1.json", {"schema": "IncidentReplayPack", "incident_id": "incident-1"})
    _write_json(
        tmp_path / ".omg" / "state" / "background-verification.json",
        {"schema": "BackgroundVerificationState", "run_id": "run-1"},
    )

    result = build_repro_pack(str(tmp_path), run_id="run-1")

    assert result["status"] == "ok"
    assert result["run_id"] == "run-1"
    assert result["path"] == ".omg/evidence/repro-pack-run-1.json"

    repro_path = tmp_path / ".omg" / "evidence" / "repro-pack-run-1.json"
    manifest = _read_manifest(repro_path)

    assert manifest["schema"] == "ReproPack"
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "run-1"
    assert manifest["evidence_pack_path"] == ".omg/evidence/run-1.json"
    assert manifest["unresolved_risks"] == ["risk:high:auth"]
    assert manifest["assembled_at"]
    assert manifest["seed"] == derive_run_seed("run-1")
    assert manifest["determinism_version"] == "forge-determinism-v1"
    assert manifest["determinism_scope"] == "same-hardware"
    assert manifest["temperature_lock"] == {
        "critical_model_paths": 0.0,
        "critical_tool_paths": 0.0,
    }

    artifact_kinds = {
        item["kind"]
        for item in _artifact_list(manifest)
        if isinstance(item.get("kind"), str)
    }
    assert "evidence_pack" in artifact_kinds
    assert "trace" in artifact_kinds
    assert "trace_events" in artifact_kinds
    assert "eval" in artifact_kinds
    assert "lineage" in artifact_kinds
    assert "security_evidence" in artifact_kinds
    assert "browser_trace" in artifact_kinds
    assert "incident_pack" in artifact_kinds
    assert "verification_state" in artifact_kinds


def test_build_repro_pack_returns_error_for_missing_run_id(tmp_path: Path) -> None:
    result = build_repro_pack(str(tmp_path), run_id="missing")

    assert result == {
        "status": "error",
        "run_id": "missing",
        "reason": "evidence_pack_not_found",
    }


def test_build_repro_pack_manifest_uses_stable_references_only(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack_payload())
    _write_jsonl(tmp_path / ".omg" / "tracebank" / "events.jsonl", [{"trace_id": "trace-1"}, {"trace_id": "trace-2"}])
    _write_json(tmp_path / ".omg" / "lineage" / "lineage-1.json", {"lineage_id": "lineage-1"})
    _write_json(tmp_path / ".omg" / "evidence" / "security-check.json", {"schema": "SecurityCheckResult"})
    (tmp_path / ".omg" / "evidence" / "browser-trace.zip").parent.mkdir(parents=True, exist_ok=True)
    _ = (tmp_path / ".omg" / "evidence" / "browser-trace.zip").write_bytes(b"browser-proof")
    _write_json(tmp_path / ".omg" / "incidents" / "incident-1.json", {"schema": "IncidentReplayPack"})

    result = build_repro_pack(str(tmp_path), run_id="run-1")
    assert result["status"] == "ok"

    manifest = _read_manifest(tmp_path / result["path"])
    artifacts = _artifact_list(manifest)

    assert len(artifacts) == len({(item["kind"], item["path"], item.get("sha256", "")) for item in artifacts})
    assert all(isinstance(item.get("path"), str) and item["path"] for item in artifacts)
    assert any(item.get("sha256") for item in artifacts)
    assert all("content" not in item and "payload" not in item for item in artifacts)


def test_build_repro_pack_returns_error_when_determinism_metadata_missing(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "evidence" / "run-1.json",
        _evidence_pack_payload(include_determinism=False),
    )

    result = build_repro_pack(str(tmp_path), run_id="run-1")

    assert result == {
        "status": "error",
        "run_id": "run-1",
        "reason": "determinism_metadata_missing",
    }
