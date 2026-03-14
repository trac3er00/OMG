from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.evidence_query import (
    get_eval,
    get_evidence_pack,
    get_lineage,
    get_trace,
    get_verification_state,
    list_evidence_packs,
    query_evidence,
)
from runtime.data_lineage import add_lineage_edge, build_lineage_manifest, traverse_lineage


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _evidence_pack(
    run_id: str,
    trace_ids: list[str] | None = None,
    *,
    evidence_profile: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
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
    if evidence_profile is not None:
        payload["evidence_profile"] = evidence_profile
    return payload


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


def test_get_evidence_pack_enriches_context_metadata_for_run(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-1.json", _evidence_pack("run-1", ["trace-1"]))
    (tmp_path / ".omg" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omg" / "state" / "profile.yaml").write_text("profile_version: profile-v31\n", encoding="utf-8")
    _write_json(
        tmp_path / ".omg" / "state" / "intent_gate" / "run-1.json",
        {
            "schema": "IntentGateDecision",
            "run_id": "run-1",
            "intent_gate_version": "1.3.0",
        },
    )
    _write_json(
        tmp_path / ".omg" / "state" / "context_engine_packet.json",
        {
            "schema": "ContextEnginePacket",
            "run_id": "run-1",
            "clarification_status": {"requires_clarification": False},
        },
    )

    pack = get_evidence_pack(str(tmp_path), "run-1")

    assert pack is not None
    assert pack["profile_version"] == "profile-v31"
    assert pack["intent_gate_version"] == "1.3.0"
    assert isinstance(pack["context_checksum"], str)
    assert len(str(pack["context_checksum"])) == 64


def test_query_evidence_enriches_jsonl_rows_with_context_metadata(tmp_path: Path) -> None:
    tracebank_path = tmp_path / ".omg" / "tracebank" / "events.jsonl"
    tracebank_path.parent.mkdir(parents=True, exist_ok=True)
    _ = tracebank_path.write_text(
        json.dumps({"schema": "TracebankRecord", "run_id": "run-1", "trace_id": "trace-1"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".omg" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omg" / "state" / "profile.yaml").write_text("profile_version: profile-v6\n", encoding="utf-8")
    _write_json(
        tmp_path / ".omg" / "state" / "intent_gate" / "run-1.json",
        {
            "schema": "IntentGateDecision",
            "run_id": "run-1",
            "schema_version": "1.0.7",
        },
    )

    rows = query_evidence(str(tmp_path), run_id="run-1")

    assert len(rows) == 1
    assert rows[0]["profile_version"] == "profile-v6"
    assert rows[0]["intent_gate_version"] == "1.0.7"
    assert isinstance(rows[0]["context_checksum"], str)


def test_query_evidence_filters_by_profile_id(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "evidence" / "run-a.json",
        {
            **_evidence_pack("run-a", ["trace-a"]),
            "profile_id": "profile-a",
        },
    )
    _write_json(
        tmp_path / ".omg" / "evidence" / "run-b.json",
        {
            **_evidence_pack("run-b", ["trace-b"]),
            "profile_id": "profile-b",
        },
    )

    rows = query_evidence(str(tmp_path), profile_id="profile-a")

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-a"
    assert rows[0]["profile_id"] == "profile-a"


def test_query_evidence_returns_artifact_handles_not_large_payloads(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "evidence" / "run-large.json",
        {
            **_evidence_pack("run-large", ["trace-large"]),
            "profile_id": "profile-large",
            "artifacts": [
                {
                    "kind": "trace_zip",
                    "path": ".omg/artifacts/run-large/trace.zip",
                    "summary": "browser trace",
                    "payload": "x" * 5000,
                }
            ],
        },
    )

    rows = query_evidence(str(tmp_path), run_id="run-large", profile_id="profile-large")

    assert len(rows) == 1
    artifacts = rows[0]["artifacts"]
    assert isinstance(artifacts, list)
    assert len(artifacts) == 1
    artifacts_list = cast(list[dict[str, object]], artifacts)
    handle_obj = artifacts_list[0]
    assert handle_obj["kind"] == "trace_zip"
    assert handle_obj["path"] == ".omg/artifacts/run-large/trace.zip"
    assert handle_obj["summary"] == "browser trace"
    assert "payload" not in handle_obj
    assert handle_obj["omitted_payload"] is True


def test_lineage_adjacency_traversal_is_scoped(tmp_path: Path) -> None:
    manifest = build_lineage_manifest(
        str(tmp_path),
        artifact_type="evidence-pack",
        sources=[{"kind": "repo", "path": "runtime/evidence_query.py", "license": "MIT"}],
        privacy="internal",
        license="MIT",
        derivation={"trace_id": "trace-l1"},
        trace_id="trace-l1",
    )
    add_lineage_edge(
        str(tmp_path),
        parent_node="trace-l1",
        child_node=str(manifest["lineage_id"]),
        edge_type="produced",
        run_id="run-lineage",
        profile_id="profile-lineage",
    )
    add_lineage_edge(
        str(tmp_path),
        parent_node="trace-l1",
        child_node="lineage-other",
        edge_type="produced",
        run_id="run-other",
        profile_id="profile-lineage",
    )

    graph = traverse_lineage(
        str(tmp_path),
        start_node="trace-l1",
        run_id="run-lineage",
        profile_id="profile-lineage",
        max_depth=2,
    )

    assert graph["start_node"] == "trace-l1"
    assert str(manifest["lineage_id"]) in graph["nodes"]
    assert "lineage-other" not in graph["nodes"]
    assert len(graph["edges"]) == 1


def test_get_evidence_pack_enriches_docs_only_requirements(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "evidence" / "run-docs.json",
        _evidence_pack("run-docs", ["trace-docs"], evidence_profile="docs-only"),
    )

    pack = get_evidence_pack(str(tmp_path), "run-docs")

    assert pack is not None
    assert pack["evidence_profile"] == "docs-only"
    assert pack["evidence_requirements"] == ["lsp_clean", "trace_link"]


def test_get_evidence_pack_missing_profile_fails_closed_to_full_requirements(tmp_path: Path) -> None:
    _write_json(tmp_path / ".omg" / "evidence" / "run-default.json", _evidence_pack("run-default", ["trace-1"]))

    pack = get_evidence_pack(str(tmp_path), "run-default")

    assert pack is not None
    assert "evidence_profile" in pack
    assert pack["evidence_profile"] == ""
    requirements = pack["evidence_requirements"]
    assert isinstance(requirements, list)
    assert "security_scan" in requirements
    assert "sbom" in requirements


def test_unknown_profile_behavior(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "evidence" / "run-unknown.json",
        _evidence_pack("run-unknown", ["trace-unknown"], evidence_profile="not-a-real-profile"),
    )

    pack = get_evidence_pack(str(tmp_path), "run-unknown")

    assert pack is not None
    assert pack["evidence_profile"] == "not-a-real-profile"
    assert pack["evidence_profile_known"] is False
    assert pack["evidence_profile_error"] == "unknown_evidence_profile:not-a-real-profile"
    requirements = pack["evidence_requirements"]
    assert isinstance(requirements, list)
    assert "security_scan" in requirements
    assert "sbom" in requirements
