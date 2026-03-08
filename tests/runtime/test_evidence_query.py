from __future__ import annotations

import json
from pathlib import Path

from runtime.evidence_query import (
    get_eval,
    get_evidence_pack,
    get_lineage,
    get_trace,
    get_verification_state,
    list_evidence_packs,
    query_evidence,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _evidence_pack(run_id: str, trace_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "schema": "EvidencePack",
        "schema_version": 2,
        "run_id": run_id,
        "tests": [],
        "security_scans": [],
        "diff_summary": {},
        "reproducibility": {},
        "unresolved_risks": [],
        "trace_ids": trace_ids or [],
        "lineage": {},
        "executor": {},
        "environment": {},
        "artifacts": [],
    }


def test_get_evidence_pack_returns_pack_for_known_run_id(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack("run-1", ["trace-1"]))

    pack = get_evidence_pack(str(tmp_path), "run-1")

    assert pack is not None
    assert pack["run_id"] == "run-1"


def test_query_evidence_filters_by_trace_id(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack("run-1", ["trace-1"]))
    _write_json(tmp_path / ".omg" / "evidence" / "run-2.json", _evidence_pack("run-2", ["trace-2"]))

    rows = query_evidence(str(tmp_path), trace_id="trace-1")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"


def test_query_evidence_filters_by_schema(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack("run-1"))
    _write_json(
        tmp_path / ".omg" / "lineage" / "lineage-1.json",
        {"schema": "LineageManifest", "schema_version": 1, "lineage_id": "lineage-1"},
    )

    rows = query_evidence(str(tmp_path), schema="LineageManifest")

    assert len(rows) == 1
    assert rows[0]["lineage_id"] == "lineage-1"


def test_get_evidence_pack_returns_none_for_missing_run_id(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack("run-1"))

    assert get_evidence_pack(str(tmp_path), "missing-run") is None


def test_query_evidence_returns_empty_list_for_empty_directory(tmp_path: Path) -> None:
    assert query_evidence(str(tmp_path)) == []


def test_malformed_json_files_are_skipped_gracefully(tmp_path: Path) -> None:
    malformed = tmp_path / ".omg" / "evidence" / "bad.json"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    _ = malformed.write_text("{not-json", encoding="utf-8")

    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack("run-1"))

    rows = query_evidence(str(tmp_path), schema="EvidencePack")
    pack = get_evidence_pack(str(tmp_path), "run-1")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"
    assert pack is not None


def test_list_evidence_packs_sorts_by_mtime_descending(tmp_path: Path) -> None:
    older = tmp_path / ".omg" / "evidence" / "run-1.json"
    newer = tmp_path / ".omg" / "evidence" / "run-2.json"
    _write_json(older, _evidence_pack("run-1"))
    _write_json(newer, _evidence_pack("run-2"))

    packs = list_evidence_packs(str(tmp_path))

    assert [pack["run_id"] for pack in packs] == ["run-2", "run-1"]


def test_get_trace_reads_jsonl_and_matches_trace_id(tmp_path: Path) -> None:
    trace_path = tmp_path / ".omg" / "tracebank" / "events.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    _ = trace_path.write_text(
        json.dumps({"trace_id": "trace-1", "status": "ok"}) + "\n"
        + json.dumps({"trace_id": "trace-2", "status": "error"})
        + "\n",
        encoding="utf-8",
    )

    trace = get_trace(str(tmp_path), "trace-2")

    assert trace is not None
    assert trace["status"] == "error"


def test_get_eval_reads_latest_json_when_present(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "evals" / "latest.json",
        {"schema": "EvalGateResult", "schema_version": 2, "trace_id": "trace-1"},
    )

    payload = get_eval(str(tmp_path))

    assert payload is not None
    assert payload["trace_id"] == "trace-1"


def test_get_lineage_reads_manifest_by_lineage_id(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "lineage" / "lineage-1.json",
        {"schema": "LineageManifest", "schema_version": 2, "lineage_id": "lineage-1"},
    )

    payload = get_lineage(str(tmp_path), "lineage-1")

    assert payload is not None
    assert payload["schema"] == "LineageManifest"


def test_get_verification_state_reads_background_state(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "state" / "background-verification.json",
        {
            "schema": "BackgroundVerificationState",
            "schema_version": 2,
            "run_id": "run-1",
            "status": "ok",
            "blockers": [],
            "evidence_links": [],
            "progress": {},
            "updated_at": "2026-03-08T00:00:00+00:00",
        },
    )

    payload = get_verification_state(str(tmp_path))

    assert payload is not None
    assert payload["run_id"] == "run-1"
